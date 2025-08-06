use std::borrow::Borrow;
use std::io::Error;
use std::mem::MaybeUninit;
use std::net::SocketAddr;
use std::pin::Pin;
use std::sync::Arc;
use std::task::{Context, Poll};

use bytes::Bytes;
use futures::stream::Stream;
use tokio::io::ReadBuf;
use tokio::net::UdpSocket;

use crate::closure::Closure;

// We need to allocate a large buffer because `UdpSocket` discards excess data.  IPv4 UDP datagrams
// are smaller than 64 KB.  UDP datagrams can be larger than 64 KB if IPv6 jumbograms are used, but
// such datagrams are likely very rare in practice.
const BUFFER_SIZE: usize = 65536;

#[derive(Debug)]
pub struct UdpStream<Socket> {
    socket: Socket,
    closure: Arc<Closure>,
    buffer: Box<[MaybeUninit<u8>]>,
}

impl<Socket> UdpStream<Socket>
where
    Socket: Borrow<UdpSocket>,
{
    pub(crate) fn new(socket: Socket, closure: Arc<Closure>) -> Self {
        Self {
            socket,
            closure,
            buffer: Box::new_uninit_slice(BUFFER_SIZE),
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
}

impl<Socket> Stream for UdpStream<Socket>
where
    Socket: Borrow<UdpSocket> + Unpin,
{
    type Item = Result<(SocketAddr, Bytes), Error>;

    fn poll_next(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        let this = self.get_mut();

        if this.is_closed() {
            return Poll::Ready(None);
        }

        let mut read = ReadBuf::uninit(&mut this.buffer);
        let read_ptr = read.filled().as_ptr();

        let poll = this.socket.borrow().poll_recv_from(cx, &mut read);
        let payload = read.filled();
        assert_eq!(read_ptr, payload.as_ptr(), "read was swapped");

        let Poll::Ready(result) = poll else {
            // We must register before checking `is_closed` to avoid race condition.
            this.closure.register(cx.waker());

            return if this.is_closed() {
                Poll::Ready(None)
            } else {
                Poll::Pending
            };
        };

        let endpoint = result?;
        let payload = Bytes::copy_from_slice(payload);

        Poll::Ready(Some(Ok((endpoint, payload))))
    }
}
