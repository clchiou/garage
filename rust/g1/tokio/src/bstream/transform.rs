use std::ops::{Deref, DerefMut};

use async_trait::async_trait;
use bytes::BytesMut;

use super::{StreamRecv, StreamSend};

/// Transformer
///
/// A transformer is a stream that consists of another stream and a transform function.  It applies
/// the transform function to the buffer data immediately after the data is written to the buffer.
///
/// The primary use case of the transformer is to add a stream cipher on top of a stream.
#[derive(Debug)]
pub struct Transformer<Stream, Transform> {
    stream: Stream,
    transform: Transform,
}

/// Transform Function
///
/// The transform function is responsible for transforming the buffer data of a stream.  Currently,
/// its interface is limited.  It is designed specifically for byte-to-byte transformations and
/// cannot be used for other types of transformations, such as block ciphers or variable-length
/// codes.
pub trait Transform {
    fn transform(&mut self, buffer: &mut [u8]);
}

/// Wraps the buffer of a `StreamSend` and transforms the buffer data when it is being dropped.
///
/// NOTE: This implementation assumes that the buffer is append-only.  If the user mutates the
/// buffer in any other manner, such as by consuming it, `SendBuffer` will transform the incorrect
/// buffer data.
#[derive(Debug)]
pub struct SendBuffer<'a, B, T>
where
    B: DerefMut<Target = BytesMut>,
    T: Transform,
{
    buffer: B,
    transform: &'a mut T,
    size: usize,
}

impl<Stream, Transform> Transformer<Stream, Transform> {
    pub fn new(stream: Stream, transform: Transform) -> Self {
        Self { stream, transform }
    }

    pub fn stream(&self) -> &Stream {
        &self.stream
    }
}

#[async_trait]
impl<S, T, E> StreamRecv for Transformer<S, T>
where
    S: StreamRecv<Error = E> + Send,
    T: Transform + Send,
{
    type Buffer<'a> = S::Buffer<'a>
    where
        Self: 'a;
    type Error = E;

    async fn recv(&mut self) -> Result<usize, Self::Error> {
        let size = self.stream.buffer().len();
        let result = self.stream.recv().await;
        self.transform.transform(&mut self.stream.buffer()[size..]);
        result
    }

    async fn recv_or_eof(&mut self) -> Result<Option<usize>, Self::Error> {
        let size = self.stream.buffer().len();
        let result = self.stream.recv_or_eof().await;
        self.transform.transform(&mut self.stream.buffer()[size..]);
        result
    }

    fn buffer(&mut self) -> Self::Buffer<'_> {
        self.stream.buffer()
    }
}

#[async_trait]
impl<S, T, E> StreamSend for Transformer<S, T>
where
    S: StreamSend<Error = E> + Send,
    T: Transform + Send,
{
    type Buffer<'a> = SendBuffer<'a, S::Buffer<'a>, T>
    where
        Self: 'a;
    type Error = E;

    fn buffer(&mut self) -> Self::Buffer<'_> {
        SendBuffer::new(self.stream.buffer(), &mut self.transform)
    }

    async fn send_all(&mut self) -> Result<(), Self::Error> {
        self.stream.send_all().await
    }

    async fn shutdown(&mut self) -> Result<(), Self::Error> {
        self.stream.shutdown().await
    }
}

impl<'a, B, T> SendBuffer<'a, B, T>
where
    B: DerefMut<Target = BytesMut>,
    T: Transform,
{
    fn new(buffer: B, transform: &'a mut T) -> Self {
        let size = buffer.len();
        Self {
            buffer,
            transform,
            size,
        }
    }
}

impl<'a, B, T> Drop for SendBuffer<'a, B, T>
where
    B: DerefMut<Target = BytesMut>,
    T: Transform,
{
    fn drop(&mut self) {
        self.transform.transform(&mut self.buffer[self.size..]);
    }
}

impl<'a, B, T> Deref for SendBuffer<'a, B, T>
where
    B: DerefMut<Target = BytesMut>,
    T: Transform,
{
    type Target = BytesMut;

    fn deref(&self) -> &Self::Target {
        self.buffer.deref()
    }
}

impl<'a, B, T> DerefMut for SendBuffer<'a, B, T>
where
    B: DerefMut<Target = BytesMut>,
    T: Transform,
{
    fn deref_mut(&mut self) -> &mut Self::Target {
        self.buffer.deref_mut()
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use bytes::BufMut;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    use crate::io::{RecvStream, SendStream};

    use super::*;

    struct Invert;

    impl Transform for Invert {
        fn transform(&mut self, buffer: &mut [u8]) {
            for x in buffer.iter_mut() {
                *x = !*x;
            }
        }
    }

    #[tokio::test]
    async fn transformer_recv() {
        let (stream, mut mock) = RecvStream::new_mock(4096);
        let mut transformer = Transformer::new(stream, Invert);

        mock.write_u8(0x01).await.unwrap();
        assert_matches!(transformer.recv().await, Ok(1));
        assert_eq!(transformer.buffer().as_ref(), &[!0x01]);

        mock.write_u8(0x02).await.unwrap();
        assert_matches!(transformer.recv_or_eof().await, Ok(Some(1)));
        assert_eq!(transformer.buffer().as_ref(), &[!0x01, !0x02]);

        mock.write_u16(0x0304).await.unwrap();
        assert_matches!(transformer.recv_fill(3).await, Ok(()));
        assert_eq!(transformer.buffer().as_ref(), &[!0x01, !0x02, !0x03, !0x04]);
    }

    #[tokio::test]
    async fn transformer_send() {
        let (stream, mut mock) = SendStream::new_mock(4096);
        let mut transformer = Transformer::new(stream, Invert);
        transformer.buffer().put_u16(0x0102);
        assert_matches!(transformer.send_all().await, Ok(()));
        assert_eq!(mock.read_u16().await.unwrap(), !0x0102);
    }
}
