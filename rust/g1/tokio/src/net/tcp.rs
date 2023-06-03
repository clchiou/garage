use bytes::BytesMut;
use tokio::net;

use crate::bstream::{StreamIntoSplit, StreamSplit};
use crate::io::{RecvStream, SendStream, Stream};

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
