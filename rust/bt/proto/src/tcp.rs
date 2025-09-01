use tokio::net::TcpStream;
use tokio::net::tcp::{OwnedReadHalf, OwnedWriteHalf, ReadHalf, WriteHalf};

use g1_tokio::frame::{FrameSink, FrameStream};

use crate::message::Codec;

pub type OwnedStream = FrameStream<OwnedReadHalf, Codec>;
pub type OwnedSink = FrameSink<OwnedWriteHalf, Codec>;

pub type Stream<'a> = FrameStream<ReadHalf<'a>, Codec>;
pub type Sink<'a> = FrameSink<WriteHalf<'a>, Codec>;

pub fn into_split(stream: TcpStream) -> (OwnedStream, OwnedSink) {
    let (r, w) = stream.into_split();
    (Codec::stream(r), Codec::sink(w))
}

pub fn split(stream: &mut TcpStream) -> (Stream, Sink) {
    let (r, w) = stream.split();
    (Codec::stream(r), Codec::sink(w))
}
