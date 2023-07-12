use std::io::{Error, ErrorKind};
use std::net::SocketAddr;
use std::sync::Arc;

use async_trait::async_trait;
use bytes::{BufMut, Bytes, BytesMut};
use tokio::{
    net::UdpSocket,
    sync::{mpsc, oneshot},
};

use g1_tokio::bstream::{StreamIntoSplit, StreamRecv, StreamSend, StreamSplit};

#[derive(Debug)]
pub struct UtpStream {
    recv: UtpRecvStream,
    send: UtpSendStream,
}

#[derive(Debug)]
pub struct UtpRecvStream {
    socket: Arc<UdpSocket>,
    peer_endpoint: SocketAddr,
    buffer: BytesMut,
    incoming_recv: IncomingRecv,
}

#[derive(Debug)]
pub struct UtpSendStream {
    socket: Arc<UdpSocket>,
    peer_endpoint: SocketAddr,
    // Wrap the buffer in an `Option` because we are moving it instead of copying its contents.
    buffer: Option<BytesMut>,
    // Wrap the sender in an `Option` so that we can gracefully close the receiver by dropping the
    // sender.
    outgoing_send: Option<OutgoingSend>,
}

g1_param::define!(incoming_queue_size: usize = 32);
const OUTGOING_QUEUE_SIZE: usize = 1;

pub(crate) type Incoming = Result<Bytes, Error>;
pub(crate) type IncomingRecv = mpsc::Receiver<Incoming>;
pub(crate) type IncomingSend = mpsc::Sender<Incoming>;

pub(crate) type Outgoing = (BytesMut, oneshot::Sender<(BytesMut, Result<(), Error>)>);
// TODO: It is overkill to use the `mpsc` channel here.  Let us simplify it.
pub(crate) type OutgoingRecv = mpsc::Receiver<Outgoing>;
pub(crate) type OutgoingSend = mpsc::Sender<Outgoing>;

fn new_broken_pipe_error() -> Error {
    Error::new(ErrorKind::BrokenPipe, "utp connection is closed")
}

fn new_unexpected_eof_error() -> Error {
    Error::new(ErrorKind::UnexpectedEof, "utp connection is closed")
}

impl UtpStream {
    pub(crate) fn new(recv: UtpRecvStream, send: UtpSendStream) -> Self {
        assert!(Arc::ptr_eq(&recv.socket, &send.socket));
        assert_eq!(recv.peer_endpoint, send.peer_endpoint);
        Self { recv, send }
    }

    pub fn socket(&self) -> &UdpSocket {
        &self.recv.socket
    }

    pub fn peer_endpoint(&self) -> SocketAddr {
        self.recv.peer_endpoint
    }
}

impl UtpRecvStream {
    pub(crate) fn new(socket: Arc<UdpSocket>, peer_endpoint: SocketAddr) -> (Self, IncomingSend) {
        let (incoming_send, incoming_recv) = mpsc::channel(*incoming_queue_size());
        (
            Self {
                socket,
                peer_endpoint,
                buffer: BytesMut::with_capacity(*bittorrent_base::recv_buffer_capacity()),
                incoming_recv,
            },
            incoming_send,
        )
    }

    pub fn socket(&self) -> &UdpSocket {
        &self.socket
    }

    pub fn peer_endpoint(&self) -> SocketAddr {
        self.peer_endpoint
    }
}

impl UtpSendStream {
    pub(crate) fn new(socket: Arc<UdpSocket>, peer_endpoint: SocketAddr) -> (Self, OutgoingRecv) {
        let (outgoing_send, outgoing_recv) = mpsc::channel(OUTGOING_QUEUE_SIZE);
        (
            Self {
                socket,
                peer_endpoint,
                buffer: Some(BytesMut::with_capacity(
                    *bittorrent_base::send_buffer_capacity(),
                )),
                outgoing_send: Some(outgoing_send),
            },
            outgoing_recv,
        )
    }

    pub fn socket(&self) -> &UdpSocket {
        &self.socket
    }

    pub fn peer_endpoint(&self) -> SocketAddr {
        self.peer_endpoint
    }
}

#[async_trait]
impl StreamRecv for UtpRecvStream {
    type Buffer<'a> = &'a mut BytesMut
    where
        Self: 'a;
    type Error = Error;

    async fn recv(&mut self) -> Result<usize, Self::Error> {
        self.recv_or_eof()
            .await?
            .ok_or_else(new_unexpected_eof_error)
    }

    async fn recv_or_eof(&mut self) -> Result<Option<usize>, Self::Error> {
        match self.incoming_recv.recv().await.transpose()? {
            Some(payload) => {
                self.buffer.put_slice(&payload);
                Ok(Some(payload.len()))
            }
            None => Ok(None),
        }
    }

    fn buffer(&mut self) -> Self::Buffer<'_> {
        &mut self.buffer
    }
}

#[async_trait]
impl StreamSend for UtpSendStream {
    type Buffer<'a> = &'a mut BytesMut
    where
        Self: 'a;
    type Error = Error;

    // I am not sure if this is a good design, but the buffer becomes unavailable after `send_all`
    // returns an error.
    fn buffer(&mut self) -> Self::Buffer<'_> {
        self.buffer.as_mut().unwrap()
    }

    async fn send_all(&mut self) -> Result<(), Self::Error> {
        // We drop both the sender and the buffer whenever we get an error.
        let outgoing_send = self
            .outgoing_send
            .as_mut()
            .ok_or_else(new_broken_pipe_error)?;
        let buffer = self.buffer.take().unwrap();
        let (result_send, result_recv) = oneshot::channel();
        if let Err(error) = outgoing_send.try_send((buffer, result_send)) {
            self.outgoing_send = None;
            return match error {
                mpsc::error::TrySendError::Full(_) => std::panic!("utp outgoing queue is full"),
                mpsc::error::TrySendError::Closed(_) => Err(new_broken_pipe_error()),
            };
        }
        match result_recv.await {
            Ok((buffer, Ok(()))) => {
                self.buffer = Some(buffer);
                Ok(())
            }
            Ok((_, err @ Err(_))) => {
                self.outgoing_send = None;
                err
            }
            Err(_) => {
                self.outgoing_send = None;
                Err(new_broken_pipe_error())
            }
        }
    }

    async fn shutdown(&mut self) -> Result<(), Self::Error> {
        self.send_all().await?;
        self.outgoing_send = None;
        Ok(())
    }
}

#[async_trait]
impl StreamRecv for UtpStream {
    type Buffer<'a> = &'a mut BytesMut
    where
        Self: 'a;
    type Error = Error;

    async fn recv(&mut self) -> Result<usize, Self::Error> {
        self.recv.recv().await
    }

    async fn recv_or_eof(&mut self) -> Result<Option<usize>, Self::Error> {
        self.recv.recv_or_eof().await
    }

    fn buffer(&mut self) -> Self::Buffer<'_> {
        self.recv.buffer()
    }
}

#[async_trait]
impl StreamSend for UtpStream {
    type Buffer<'a> = &'a mut BytesMut
    where
        Self: 'a;
    type Error = Error;

    fn buffer(&mut self) -> Self::Buffer<'_> {
        self.send.buffer()
    }

    async fn send_all(&mut self) -> Result<(), Self::Error> {
        self.send.send_all().await
    }

    async fn shutdown(&mut self) -> Result<(), Self::Error> {
        self.send.shutdown().await
    }
}

// TODO: Figure out why the generic implementation of `StreamRecv` and `StreamSend` for `&mut T`
// cannot be used in implementing `StreamSplit`.

#[async_trait]
impl StreamRecv for &mut UtpRecvStream {
    type Buffer<'a> = &'a mut BytesMut
    where
        Self: 'a;
    type Error = Error;

    async fn recv(&mut self) -> Result<usize, Self::Error> {
        (*self).recv().await
    }

    async fn recv_or_eof(&mut self) -> Result<Option<usize>, Self::Error> {
        (*self).recv_or_eof().await
    }

    async fn recv_fill(&mut self, min_size: usize) -> Result<(), Self::Error> {
        (*self).recv_fill(min_size).await
    }

    fn buffer(&mut self) -> Self::Buffer<'_> {
        (*self).buffer()
    }
}

#[async_trait]
impl StreamSend for &mut UtpSendStream {
    type Buffer<'a> = &'a mut BytesMut
    where
        Self: 'a;
    type Error = Error;

    fn buffer(&mut self) -> Self::Buffer<'_> {
        (*self).buffer()
    }

    async fn send_all(&mut self) -> Result<(), Self::Error> {
        (*self).send_all().await
    }

    async fn shutdown(&mut self) -> Result<(), Self::Error> {
        (*self).shutdown().await
    }
}

impl StreamSplit for UtpStream {
    type RecvHalf<'a> = &'a mut UtpRecvStream;
    type SendHalf<'a> = &'a mut UtpSendStream;

    fn split(&mut self) -> (Self::RecvHalf<'_>, Self::SendHalf<'_>) {
        (&mut self.recv, &mut self.send)
    }
}

impl StreamIntoSplit for UtpStream {
    type OwnedRecvHalf = UtpRecvStream;
    type OwnedSendHalf = UtpSendStream;

    fn into_split(self) -> (Self::OwnedRecvHalf, Self::OwnedSendHalf) {
        (self.recv, self.send)
    }

    fn reunite(
        recv: Self::OwnedRecvHalf,
        send: Self::OwnedSendHalf,
    ) -> Result<Self, (Self::OwnedRecvHalf, Self::OwnedSendHalf)> {
        if Arc::ptr_eq(&recv.socket, &send.socket) {
            Ok(Self::new(recv, send))
        } else {
            Err((recv, send))
        }
    }
}
