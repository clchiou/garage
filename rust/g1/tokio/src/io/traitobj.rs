use std::io::Error;

use async_trait::async_trait;
use bytes::BytesMut;

use crate::bstream::{SendBuffer, StreamBuffer, StreamRecv, StreamSend};

// TODO: How to support `StreamSplit` and `StreamIntoSplit`?  (Their use of associated types makes
// this hard.)
pub type DynStream<'stream> = Box<dyn Stream + Send + 'stream>;
pub type DynStreamRecv<'stream> = Box<dyn StreamRecv<Error = Error> + Send + 'stream>;
pub type DynStreamSend<'stream> = Box<dyn StreamSend<Error = Error> + Send + 'stream>;

#[async_trait]
impl StreamRecv for DynStream<'_> {
    type Error = Error;

    async fn recv(&mut self) -> Result<usize, Self::Error> {
        (**self).recv().await
    }

    async fn recv_or_eof(&mut self) -> Result<Option<usize>, Self::Error> {
        (**self).recv_or_eof().await
    }

    fn buffer(&mut self) -> &mut BytesMut {
        StreamRecv::buffer(&mut **self)
    }
}

#[async_trait]
impl StreamRecv for DynStreamRecv<'_> {
    type Error = Error;

    async fn recv(&mut self) -> Result<usize, Self::Error> {
        (**self).recv().await
    }

    async fn recv_or_eof(&mut self) -> Result<Option<usize>, Self::Error> {
        (**self).recv_or_eof().await
    }

    fn buffer(&mut self) -> &mut BytesMut {
        (**self).buffer()
    }
}

#[async_trait]
impl StreamSend for DynStream<'_> {
    type Error = Error;

    fn buffer(&mut self) -> SendBuffer<'_> {
        StreamSend::buffer(&mut **self)
    }

    async fn send_all(&mut self) -> Result<(), Self::Error> {
        (**self).send_all().await
    }

    async fn shutdown(&mut self) -> Result<(), Self::Error> {
        (**self).shutdown().await
    }
}

#[async_trait]
impl StreamSend for DynStreamSend<'_> {
    type Error = Error;

    fn buffer(&mut self) -> SendBuffer<'_> {
        (**self).buffer()
    }

    async fn send_all(&mut self) -> Result<(), Self::Error> {
        (**self).send_all().await
    }

    async fn shutdown(&mut self) -> Result<(), Self::Error> {
        (**self).shutdown().await
    }
}

pub trait Stream
where
    Self: StreamBuffer,
    Self: StreamRecv<Error = Error>,
    Self: StreamSend<Error = Error>,
{
}

impl<T> Stream for T
where
    T: StreamBuffer,
    T: StreamRecv<Error = Error>,
    T: StreamSend<Error = Error>,
{
}
