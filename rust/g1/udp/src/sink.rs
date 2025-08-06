use std::borrow::Borrow;
use std::io::{Error, ErrorKind};
use std::net::SocketAddr;
use std::pin::Pin;
use std::sync::Arc;
use std::task::{self, Context, Poll};

use bytes::Bytes;
use futures::sink::Sink;
use tokio::net::UdpSocket;

use crate::closure::Closure;

#[derive(Debug)]
pub struct UdpSink<Socket> {
    socket: Socket,
    closure: Arc<Closure>,
    item: Option<(SocketAddr, Bytes)>,
}

impl<Socket> UdpSink<Socket>
where
    Socket: Borrow<UdpSocket>,
{
    pub(crate) fn new(socket: Socket, closure: Arc<Closure>) -> Self {
        Self {
            socket,
            closure,
            item: None,
        }
    }

    pub fn is_closed(&self) -> bool {
        self.closure.get()
    }

    pub fn socket(&self) -> &UdpSocket {
        self.socket.borrow()
    }

    pub fn into_socket(self) -> Socket {
        self.socket
    }

    fn ensure_open(&self) -> Result<(), Error> {
        if self.is_closed() {
            Err(Error::from(ErrorKind::BrokenPipe))
        } else {
            Ok(())
        }
    }
}

impl<Socket> Sink<(SocketAddr, Bytes)> for UdpSink<Socket>
where
    Socket: Borrow<UdpSocket> + Unpin,
{
    type Error = Error;

    fn poll_ready(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        self.ensure_open()?;
        let () = task::ready!(self.poll_flush(cx))?;
        Poll::Ready(Ok(()))
    }

    fn start_send(self: Pin<&mut Self>, item: (SocketAddr, Bytes)) -> Result<(), Self::Error> {
        self.ensure_open()?;
        assert!(self.get_mut().item.replace(item).is_none());
        Ok(())
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        let Some((endpoint, ref payload)) = self.item else {
            return Poll::Ready(Ok(()));
        };

        self.ensure_open()?;

        let num_sent = task::ready!(self.socket.borrow().poll_send_to(cx, payload, endpoint))?;
        let expect = payload.len();

        // It appears to be the right decision not to re-send a datagram after it has been
        // partially sent.
        self.get_mut().item = None;

        Poll::Ready(if num_sent == expect {
            Ok(())
        } else {
            Err(Error::other(format!(
                "udp partial send: {endpoint} {num_sent} < {expect}",
            )))
        })
    }

    fn poll_close(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        let () = task::ready!(self.as_mut().poll_flush(cx))?;
        self.closure.set();
        Poll::Ready(Ok(()))
    }
}
