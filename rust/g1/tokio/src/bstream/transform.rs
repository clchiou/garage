use std::ops::{Deref, DerefMut};

use async_trait::async_trait;
use bytes::BytesMut;

use super::{StreamIntoSplit, StreamRecv, StreamSend, StreamSplit};

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

/// It is similar to the `Transformer`, except that it has two transform functions that are applied
/// to traffic in both directions.
#[derive(Debug)]
pub struct DuplexTransformer<Stream, RecvTransform, SendTransform> {
    stream: Stream,
    recv_transform: RecvTransform,
    send_transform: SendTransform,
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

macro_rules! recv {
    ($stream:expr, $transform:expr $(,)?) => {{
        let size = $stream.buffer().len();
        let result = $stream.recv().await;
        $transform.transform(&mut $stream.buffer()[size..]);
        result
    }};
}

macro_rules! recv_or_eof {
    ($stream:expr, $transform:expr $(,)?) => {{
        let size = $stream.buffer().len();
        let result = $stream.recv_or_eof().await;
        $transform.transform(&mut $stream.buffer()[size..]);
        result
    }};
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
        recv!(self.stream, self.transform)
    }

    async fn recv_or_eof(&mut self) -> Result<Option<usize>, Self::Error> {
        recv_or_eof!(self.stream, self.transform)
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

impl<T> Transform for &mut T
where
    T: Transform,
{
    fn transform(&mut self, buffer: &mut [u8]) {
        (*self).transform(buffer)
    }
}

impl Transform for Box<dyn Transform + Send> {
    fn transform(&mut self, buffer: &mut [u8]) {
        (**self).transform(buffer)
    }
}

impl<Stream, RecvTransform, SendTransform> DuplexTransformer<Stream, RecvTransform, SendTransform> {
    pub fn new(
        stream: Stream,
        recv_transform: RecvTransform,
        send_transform: SendTransform,
    ) -> Self {
        Self {
            stream,
            recv_transform,
            send_transform,
        }
    }

    pub fn stream(&self) -> &Stream {
        &self.stream
    }
}

#[async_trait]
impl<Stream, RecvTransform, SendTransform, Error> StreamRecv
    for DuplexTransformer<Stream, RecvTransform, SendTransform>
where
    Stream: StreamRecv<Error = Error> + Send,
    RecvTransform: Transform + Send,
    SendTransform: Send,
{
    type Buffer<'a> = Stream::Buffer<'a>
    where
        Self: 'a;
    type Error = Error;

    async fn recv(&mut self) -> Result<usize, Self::Error> {
        recv!(self.stream, self.recv_transform)
    }

    async fn recv_or_eof(&mut self) -> Result<Option<usize>, Self::Error> {
        recv_or_eof!(self.stream, self.recv_transform)
    }

    fn buffer(&mut self) -> Self::Buffer<'_> {
        self.stream.buffer()
    }
}

#[async_trait]
impl<Stream, RecvTransform, SendTransform, Error> StreamSend
    for DuplexTransformer<Stream, RecvTransform, SendTransform>
where
    Stream: StreamSend<Error = Error> + Send,
    RecvTransform: Send,
    SendTransform: Transform + Send,
{
    type Buffer<'a> = SendBuffer<'a, Stream::Buffer<'a>, SendTransform>
    where
        Self: 'a;
    type Error = Error;

    fn buffer(&mut self) -> Self::Buffer<'_> {
        SendBuffer::new(self.stream.buffer(), &mut self.send_transform)
    }

    async fn send_all(&mut self) -> Result<(), Self::Error> {
        self.stream.send_all().await
    }

    async fn shutdown(&mut self) -> Result<(), Self::Error> {
        self.stream.shutdown().await
    }
}

impl<Stream, RecvTransform, SendTransform> StreamSplit
    for DuplexTransformer<Stream, RecvTransform, SendTransform>
where
    Stream: StreamSplit,
    for<'a> Stream::RecvHalf<'a>: Send,
    for<'a> Stream::SendHalf<'a>: Send,
    RecvTransform: Transform + Send,
    SendTransform: Transform + Send,
{
    type RecvHalf<'a> = Transformer<Stream::RecvHalf<'a>, &'a mut RecvTransform>
    where
        Self: 'a;
    type SendHalf<'a> = Transformer<Stream::SendHalf<'a>, &'a mut SendTransform>
    where
        Self: 'a;

    fn split(&mut self) -> (Self::RecvHalf<'_>, Self::SendHalf<'_>) {
        let (recv_half, send_half) = self.stream.split();
        (
            Transformer::new(recv_half, &mut self.recv_transform),
            Transformer::new(send_half, &mut self.send_transform),
        )
    }
}

impl<Stream, RecvTransform, SendTransform> StreamIntoSplit
    for DuplexTransformer<Stream, RecvTransform, SendTransform>
where
    Stream: StreamIntoSplit,
    Stream::OwnedRecvHalf: Send,
    Stream::OwnedSendHalf: Send,
    RecvTransform: Transform + Send,
    SendTransform: Transform + Send,
{
    type OwnedRecvHalf = Transformer<Stream::OwnedRecvHalf, RecvTransform>;
    type OwnedSendHalf = Transformer<Stream::OwnedSendHalf, SendTransform>;

    fn into_split(self) -> (Self::OwnedRecvHalf, Self::OwnedSendHalf) {
        let (recv_half, send_half) = self.stream.into_split();
        (
            Transformer::new(recv_half, self.recv_transform),
            Transformer::new(send_half, self.send_transform),
        )
    }

    fn reunite(
        recv: Self::OwnedRecvHalf,
        send: Self::OwnedSendHalf,
    ) -> Result<Self, (Self::OwnedRecvHalf, Self::OwnedSendHalf)> {
        match Stream::reunite(recv.stream, send.stream) {
            Ok(stream) => Ok(Self::new(stream, recv.transform, send.transform)),
            Err((recv_half, send_half)) => Err((
                Transformer::new(recv_half, recv.transform),
                Transformer::new(send_half, send.transform),
            )),
        }
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::fmt;

    use bytes::BufMut;
    use tokio::io::{AsyncReadExt, AsyncWriteExt, DuplexStream};

    use crate::io::{RecvStream, SendStream, Stream};

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
        test_transformer_recv(&mut transformer, &mut mock).await;
    }

    async fn test_transformer_recv<T>(transformer: &mut T, mock: &mut DuplexStream)
    where
        T: StreamRecv + Send,
        T::Error: fmt::Debug,
    {
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
        test_transformer_send(&mut transformer, &mut mock).await;
    }

    async fn test_transformer_send<T>(transformer: &mut T, mock: &mut DuplexStream)
    where
        T: StreamSend + Send,
        T::Error: fmt::Debug,
    {
        transformer.buffer().put_u16(0x0102);
        assert_matches!(transformer.send_all().await, Ok(()));
        assert_eq!(mock.read_u16().await.unwrap(), !0x0102);
    }

    #[tokio::test]
    async fn duplex_transformer() {
        let (stream, mut mock) = Stream::new_mock(4096);
        let mut transformer = DuplexTransformer::new(stream, Invert, Invert);
        test_transformer_recv(&mut transformer, &mut mock).await;
        test_transformer_send(&mut transformer, &mut mock).await;
    }
}
