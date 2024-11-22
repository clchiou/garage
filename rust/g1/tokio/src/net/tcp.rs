use bytes::BytesMut;
use tokio::net;

use crate::bstream::{StreamIntoSplit, StreamSplit};
use crate::io::{RecvStream, SendStream, Stream};

#[cfg(feature = "param")]
pub use self::param::TcpListenerBuilder;

pub type TcpStream = Stream<net::TcpStream>;

pub type RecvHalf<'a> = RecvStream<net::tcp::ReadHalf<'a>, &'a mut BytesMut>;
pub type SendHalf<'a> = SendStream<net::tcp::WriteHalf<'a>, &'a mut BytesMut>;

pub type OwnedRecvHalf = RecvStream<net::tcp::OwnedReadHalf, BytesMut>;
pub type OwnedSendHalf = SendStream<net::tcp::OwnedWriteHalf, BytesMut>;

impl From<net::TcpStream> for TcpStream {
    fn from(stream: net::TcpStream) -> Self {
        Self::new(stream)
    }
}

impl TcpStream {
    pub fn stream(&self) -> &net::TcpStream {
        &self.stream
    }
}

impl StreamSplit for TcpStream {
    type RecvHalf<'a> = RecvHalf<'a>;
    type SendHalf<'a> = SendHalf<'a>;

    fn split(&mut self) -> (Self::RecvHalf<'_>, Self::SendHalf<'_>) {
        let (read_half, write_half) = self.stream.split();
        (
            Self::RecvHalf::new(read_half, &mut self.recv_buffer),
            Self::SendHalf::new(write_half, &mut self.send_buffer),
        )
    }
}

impl StreamIntoSplit for TcpStream {
    type OwnedRecvHalf = OwnedRecvHalf;
    type OwnedSendHalf = OwnedSendHalf;

    fn into_split(self) -> (Self::OwnedRecvHalf, Self::OwnedSendHalf) {
        let (read_half, write_half) = self.stream.into_split();
        (
            Self::OwnedRecvHalf::new(read_half, self.recv_buffer),
            Self::OwnedSendHalf::new(write_half, self.send_buffer),
        )
    }

    fn reunite(
        recv: Self::OwnedRecvHalf,
        send: Self::OwnedSendHalf,
    ) -> Result<Self, (Self::OwnedRecvHalf, Self::OwnedSendHalf)> {
        match recv.stream.reunite(send.stream) {
            Ok(stream) => Ok(Self::from_parts(stream, recv.buffer, send.buffer)),
            Err(net::tcp::ReuniteError(read_half, write_half)) => Err((
                Self::OwnedRecvHalf::new(read_half, recv.buffer),
                Self::OwnedSendHalf::new(write_half, send.buffer),
            )),
        }
    }
}

#[cfg(feature = "param")]
mod param {
    use std::io::Error;
    use std::net::SocketAddr;

    use serde::Deserialize;
    use tokio::net::{TcpListener, TcpSocket};

    #[derive(Clone, Debug, Deserialize)]
    #[serde(default, deny_unknown_fields)]
    pub struct TcpListenerBuilder {
        pub endpoint: SocketAddr,
        pub reuseaddr: Option<bool>,
        pub reuseport: Option<bool>,
        pub backlog: u32,
    }

    impl Default for TcpListenerBuilder {
        fn default() -> Self {
            Self {
                endpoint: "0.0.0.0:0".parse().expect("endpoint"),
                reuseaddr: None,
                reuseport: Some(true),
                backlog: 1024,
            }
        }
    }

    impl TcpListenerBuilder {
        pub fn build(&self) -> Result<(TcpListener, SocketAddr), Error> {
            let socket = if self.endpoint.is_ipv4() {
                TcpSocket::new_v4()
            } else {
                assert!(self.endpoint.is_ipv6());
                TcpSocket::new_v6()
            }?;

            if let Some(reuseaddr) = self.reuseaddr {
                socket.set_reuseaddr(reuseaddr)?;
            }
            if let Some(reuseport) = self.reuseport {
                socket.set_reuseport(reuseport)?;
            }

            socket.bind(self.endpoint)?;

            let listener = socket.listen(self.backlog)?;
            let endpoint = listener.local_addr()?;

            Ok((listener, endpoint))
        }
    }
}
