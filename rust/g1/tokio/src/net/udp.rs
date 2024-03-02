use std::borrow::Borrow;
use std::io::{Error, ErrorKind};
use std::net::SocketAddr;
use std::pin::Pin;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};
use std::task::{Context, Poll};

use bytes::Bytes;
use futures::{sink::Sink, stream::Stream};
use tokio::{io::ReadBuf, net};

use g1_base::task::WakerCell;

// IPv4 UDP datagrams are smaller than 64 KB.  UDP datagrams may be bigger than 64 KB if IPv6
// jumbograms are used, but such datagrams are probably very rare in practice.
const BUFFER_CAPACITY: usize = 65536;

#[derive(Debug)]
pub struct UdpSocket<Socket = net::UdpSocket>
where
    Socket: Borrow<net::UdpSocket>,
{
    socket: Socket,
    eof: AtomicBool,
    recv_buffer: Box<[u8]>,
    send_item: Option<(SocketAddr, Bytes)>,
    poll_next_waker: WakerCell,
}

#[derive(Debug)]
pub struct UdpStream<'a> {
    socket: &'a net::UdpSocket,
    eof: &'a AtomicBool,
    recv_buffer: &'a mut [u8],
    poll_next_waker: &'a WakerCell,
}

#[derive(Debug)]
pub struct UdpSink<'a> {
    socket: &'a net::UdpSocket,
    eof: &'a AtomicBool,
    send_item: &'a mut Option<(SocketAddr, Bytes)>,
    poll_next_waker: &'a WakerCell,
}

#[derive(Debug)]
pub struct OwnedUdpStream {
    socket: Arc<net::UdpSocket>,
    eof: Arc<AtomicBool>,
    recv_buffer: Box<[u8]>,
    poll_next_waker: Arc<WakerCell>,
}

#[derive(Debug)]
pub struct OwnedUdpSink {
    socket: Arc<net::UdpSocket>,
    eof: Arc<AtomicBool>,
    send_item: Option<(SocketAddr, Bytes)>,
    poll_next_waker: Arc<WakerCell>,
}

impl From<net::UdpSocket> for UdpSocket {
    fn from(socket: net::UdpSocket) -> Self {
        Self::new(socket)
    }
}

impl From<Arc<net::UdpSocket>> for UdpSocket<Arc<net::UdpSocket>> {
    fn from(socket: Arc<net::UdpSocket>) -> Self {
        Self::new(socket)
    }
}

impl<Socket> UdpSocket<Socket>
where
    Socket: Borrow<net::UdpSocket>,
{
    pub fn new(socket: Socket) -> Self {
        Self {
            socket,
            eof: AtomicBool::new(false),
            recv_buffer: Box::from([0u8; BUFFER_CAPACITY]),
            send_item: None,
            poll_next_waker: WakerCell::new(),
        }
    }

    pub fn socket(&self) -> &net::UdpSocket {
        self.socket.borrow()
    }

    // NOTE: This method name conflicts with `StreamExt::split` (though I think `StreamExt::split`
    // should actually be named `into_split`).
    pub fn split(&mut self) -> (UdpStream, UdpSink) {
        (
            UdpStream {
                socket: self.socket.borrow(),
                eof: &self.eof,
                recv_buffer: &mut self.recv_buffer,
                poll_next_waker: &self.poll_next_waker,
            },
            UdpSink {
                socket: self.socket.borrow(),
                eof: &self.eof,
                send_item: &mut self.send_item,
                poll_next_waker: &self.poll_next_waker,
            },
        )
    }
}

impl UdpSocket<net::UdpSocket> {
    pub fn into_split(self) -> (OwnedUdpStream, OwnedUdpSink) {
        UdpSocket {
            socket: Arc::new(self.socket),
            eof: self.eof,
            recv_buffer: self.recv_buffer,
            send_item: self.send_item,
            poll_next_waker: self.poll_next_waker,
        }
        .into_split()
    }
}

impl UdpSocket<Arc<net::UdpSocket>> {
    pub fn into_split(self) -> (OwnedUdpStream, OwnedUdpSink) {
        let UdpSocket {
            socket,
            eof,
            recv_buffer,
            send_item,
            poll_next_waker,
        } = self;
        let eof = Arc::new(eof);
        let poll_next_waker = Arc::new(poll_next_waker);
        (
            OwnedUdpStream {
                socket: socket.clone(),
                eof: eof.clone(),
                recv_buffer,
                poll_next_waker: poll_next_waker.clone(),
            },
            OwnedUdpSink {
                socket,
                eof,
                send_item,
                poll_next_waker,
            },
        )
    }
}

impl<'a> UdpStream<'a> {
    pub fn socket(&self) -> &net::UdpSocket {
        self.socket
    }
}

impl<'a> UdpSink<'a> {
    pub fn socket(&self) -> &net::UdpSocket {
        self.socket
    }
}

impl OwnedUdpStream {
    pub fn socket(&self) -> &net::UdpSocket {
        &self.socket
    }
}

impl OwnedUdpSink {
    pub fn socket(&self) -> &net::UdpSocket {
        &self.socket
    }
}

macro_rules! gen_stream_impl {
    () => {
        type Item = Result<(SocketAddr, Bytes), Error>;

        fn poll_next(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Option<Self::Item>> {
            let this = self.get_mut();

            if this.eof.load(Ordering::SeqCst) {
                this.poll_next_waker.clear();
                return Poll::Ready(None);
            }

            let mut buffer = ReadBuf::new(&mut this.recv_buffer);
            let poll = this
                .socket
                .poll_recv_from(context, &mut buffer)
                .map(|result| {
                    Some(result.map(|peer| (peer, Bytes::copy_from_slice(buffer.filled()))))
                });

            if poll.is_pending() {
                this.poll_next_waker.update(context);
            } else {
                this.poll_next_waker.clear();
            }

            poll
        }
    };
}

impl Stream for UdpSocket {
    gen_stream_impl!();
}

impl<'a> Stream for UdpStream<'a> {
    gen_stream_impl!();
}

impl Stream for OwnedUdpStream {
    gen_stream_impl!();
}

macro_rules! gen_sink_impl {
    () => {
        type Error = Error;

        fn poll_ready(
            self: Pin<&mut Self>,
            context: &mut Context<'_>,
        ) -> Poll<Result<(), Self::Error>> {
            let this = self.get_mut();
            if this.eof.load(Ordering::SeqCst) {
                return Poll::Ready(Err(Error::from(ErrorKind::BrokenPipe)));
            }
            poll_send_to(&this.socket, context, &mut this.send_item)
        }

        fn start_send(self: Pin<&mut Self>, item: (SocketAddr, Bytes)) -> Result<(), Self::Error> {
            let _ = self.get_mut().send_item.insert(item);
            Ok(())
        }

        fn poll_flush(
            self: Pin<&mut Self>,
            context: &mut Context<'_>,
        ) -> Poll<Result<(), Self::Error>> {
            let this = self.get_mut();
            if this.eof.load(Ordering::SeqCst) {
                return Poll::Ready(Err(Error::from(ErrorKind::BrokenPipe)));
            }
            poll_send_to(&this.socket, context, &mut this.send_item)
        }

        fn poll_close(
            self: Pin<&mut Self>,
            context: &mut Context<'_>,
        ) -> Poll<Result<(), Self::Error>> {
            let this = self.get_mut();

            if this.eof.load(Ordering::SeqCst) {
                // Should we allow `poll_close` on a sink that is already closed?
                return Poll::Ready(Err(Error::from(ErrorKind::BrokenPipe)));
            }

            let poll = poll_send_to(&this.socket, context, &mut this.send_item);

            if poll.is_ready() {
                this.eof.store(true, Ordering::SeqCst);
                this.poll_next_waker.wake();
            }

            poll
        }
    };
}

fn poll_send_to(
    socket: &net::UdpSocket,
    context: &mut Context<'_>,
    send_item: &mut Option<(SocketAddr, Bytes)>,
) -> Poll<Result<(), Error>> {
    let Some((peer, payload)) = send_item else {
        return Poll::Ready(Ok(()));
    };
    let poll = socket.poll_send_to(context, payload, *peer).map(|result| {
        result.and_then(|size| {
            if size == payload.len() {
                Ok(())
            } else {
                Err(Error::other(format!(
                    "only a partial payload is sent: {} actual={} expect={}",
                    peer,
                    size,
                    payload.len(),
                )))
            }
        })
    });
    if poll.is_ready() {
        *send_item = None;
    }
    poll
}

impl Sink<(SocketAddr, Bytes)> for UdpSocket {
    gen_sink_impl!();
}

impl<'a> Sink<(SocketAddr, Bytes)> for UdpSink<'a> {
    gen_sink_impl!();
}

impl Sink<(SocketAddr, Bytes)> for OwnedUdpSink {
    gen_sink_impl!();
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use futures::{sink::SinkExt, stream::StreamExt};

    use super::*;

    #[tokio::test]
    async fn stream() {
        async fn test<S>(mut stream: S, addr: SocketAddr)
        where
            S: Stream<Item = Result<(SocketAddr, Bytes), Error>> + Unpin,
        {
            let mock = net::UdpSocket::bind("127.0.0.1:0").await.unwrap();
            let mock_addr = mock.local_addr().unwrap();

            mock.send_to(b"spam egg", addr).await.unwrap();
            assert_matches!(
                stream.next().await,
                Some(Ok((peer, payload))) if peer == mock_addr && payload.as_ref() == b"spam egg",
            );

            mock.send_to(b"foo", addr).await.unwrap();
            mock.send_to(b"", addr).await.unwrap();
            mock.send_to(b"bar", addr).await.unwrap();
            assert_matches!(
                stream.next().await,
                Some(Ok((peer, payload))) if peer == mock_addr && payload.as_ref() == b"foo",
            );
            assert_matches!(
                stream.next().await,
                Some(Ok((peer, payload))) if peer == mock_addr && payload.as_ref() == b"",
            );
            assert_matches!(
                stream.next().await,
                Some(Ok((peer, payload))) if peer == mock_addr && payload.as_ref() == b"bar",
            );
        }

        let socket = UdpSocket::new(net::UdpSocket::bind("127.0.0.1:0").await.unwrap());
        let addr = socket.socket().local_addr().unwrap();
        test(socket, addr).await;

        let mut socket = UdpSocket::new(net::UdpSocket::bind("127.0.0.1:0").await.unwrap());
        let (stream, _) = UdpSocket::split(&mut socket);
        let addr = stream.socket().local_addr().unwrap();
        test(stream, addr).await;

        let socket = UdpSocket::new(net::UdpSocket::bind("127.0.0.1:0").await.unwrap());
        let (stream, _) = socket.into_split();
        let addr = stream.socket().local_addr().unwrap();
        test(stream, addr).await;
    }

    #[tokio::test]
    async fn sink() {
        async fn test<S>(mut sink: S, addr: SocketAddr)
        where
            S: Sink<(SocketAddr, Bytes), Error = Error> + Unpin,
        {
            let mock = net::UdpSocket::bind("127.0.0.1:0").await.unwrap();
            let mock_addr = mock.local_addr().unwrap();
            let mut buffer = [0u8; 256];

            assert_matches!(
                sink.send((mock_addr, Bytes::from_static(b"foo"))).await,
                Ok(()),
            );
            assert_matches!(mock.recv_from(&mut buffer).await, Ok((3, this)) if this == addr);
            assert_eq!(&buffer[..3], b"foo");

            assert_matches!(
                sink.feed((mock_addr, Bytes::from_static(b"spam"))).await,
                Ok(()),
            );
            assert_matches!(
                sink.feed((mock_addr, Bytes::from_static(b""))).await,
                Ok(()),
            );
            assert_matches!(
                sink.feed((mock_addr, Bytes::from_static(b"egg"))).await,
                Ok(()),
            );
            assert_matches!(sink.flush().await, Ok(()));
            assert_matches!(mock.recv_from(&mut buffer).await, Ok((4, this)) if this == addr);
            assert_eq!(&buffer[..4], b"spam");
            assert_matches!(mock.recv_from(&mut buffer).await, Ok((0, this)) if this == addr);
            assert_matches!(mock.recv_from(&mut buffer).await, Ok((3, this)) if this == addr);
            assert_eq!(&buffer[..3], b"egg");

            assert_matches!(sink.close().await, Ok(()));
            assert_matches!(
                sink.feed((mock_addr, Bytes::from_static(b"x"))).await,
                Err(e) if e.kind() == ErrorKind::BrokenPipe,
            );
            assert_matches!(sink.flush().await, Err(e) if e.kind() == ErrorKind::BrokenPipe);
            assert_matches!(sink.close().await, Err(e) if e.kind() == ErrorKind::BrokenPipe);
        }

        let socket = UdpSocket::new(net::UdpSocket::bind("127.0.0.1:0").await.unwrap());
        let addr = socket.socket().local_addr().unwrap();
        test(socket, addr).await;

        let mut socket = UdpSocket::new(net::UdpSocket::bind("127.0.0.1:0").await.unwrap());
        let (_, sink) = UdpSocket::split(&mut socket);
        let addr = sink.socket().local_addr().unwrap();
        test(sink, addr).await;

        let socket = UdpSocket::new(net::UdpSocket::bind("127.0.0.1:0").await.unwrap());
        let (_, sink) = socket.into_split();
        let addr = sink.socket().local_addr().unwrap();
        test(sink, addr).await;
    }

    #[tokio::test]
    async fn close_unblock_stream() {
        let mut socket = UdpSocket::new(net::UdpSocket::bind("127.0.0.1:0").await.unwrap());
        let (mut stream, mut sink) = UdpSocket::split(&mut socket);
        assert_matches!(tokio::join!(stream.next(), sink.close()), (None, Ok(())));

        let socket = UdpSocket::new(net::UdpSocket::bind("127.0.0.1:0").await.unwrap());
        let (mut stream, mut sink) = socket.into_split();
        assert_matches!(tokio::join!(stream.next(), sink.close()), (None, Ok(())));
    }
}
