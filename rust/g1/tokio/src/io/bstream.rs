//! Implements streams on top of `AsyncReadExt` and `AsyncWriteExt`.

use std::borrow::BorrowMut;
use std::io::{Error, ErrorKind};
use std::marker::Unpin;

use async_trait::async_trait;
use bytes::BytesMut;
use tokio::io::{AsyncReadExt, AsyncWriteExt};

use crate::bstream::{SendBuffer, StreamRecv, StreamSend};

#[derive(Debug)]
pub struct Stream<SubStream> {
    pub(crate) stream: SubStream,
    pub(crate) recv_buffer: BytesMut,
    pub(crate) send_buffer: BytesMut,
}

#[derive(Debug)]
pub struct RecvStream<SubStream, Buffer> {
    pub(crate) stream: SubStream,
    pub(crate) buffer: Buffer,
}

#[derive(Debug)]
pub struct SendStream<SubStream, Buffer> {
    pub(crate) stream: SubStream,
    pub(crate) buffer: Buffer,
}

impl<SubStream> Stream<SubStream> {
    pub fn new(stream: SubStream) -> Self {
        Self {
            stream,
            recv_buffer: BytesMut::new(),
            send_buffer: BytesMut::new(),
        }
    }

    pub fn with_capacity(stream: SubStream, recv_capacity: usize, send_capacity: usize) -> Self {
        Self {
            stream,
            recv_buffer: BytesMut::with_capacity(recv_capacity),
            send_buffer: BytesMut::with_capacity(send_capacity),
        }
    }

    pub(crate) fn from_parts(
        stream: SubStream,
        recv_buffer: BytesMut,
        send_buffer: BytesMut,
    ) -> Self {
        Self {
            stream,
            recv_buffer,
            send_buffer,
        }
    }
}

impl<SubStream, Buffer> RecvStream<SubStream, Buffer> {
    pub(crate) fn new(stream: SubStream, buffer: Buffer) -> Self {
        Self { stream, buffer }
    }
}

impl<SubStream, Buffer> SendStream<SubStream, Buffer> {
    pub(crate) fn new(stream: SubStream, buffer: Buffer) -> Self {
        Self { stream, buffer }
    }
}

#[async_trait]
impl<SubStream> StreamRecv for Stream<SubStream>
where
    SubStream: AsyncReadExt + Send + Unpin,
{
    type Error = Error;

    async fn recv(&mut self) -> Result<usize, Self::Error> {
        self.recv_or_eof()
            .await?
            .ok_or_else(|| Error::from(ErrorKind::UnexpectedEof))
    }

    async fn recv_or_eof(&mut self) -> Result<Option<usize>, Self::Error> {
        let size = self.stream.read_buf(&mut self.recv_buffer).await?;
        if size == 0 {
            Ok(None)
        } else {
            Ok(Some(size))
        }
    }

    fn buffer(&mut self) -> &mut BytesMut {
        &mut self.recv_buffer
    }
}

#[async_trait]
impl<SubStream> StreamSend for Stream<SubStream>
where
    SubStream: AsyncWriteExt + Send + Unpin,
{
    type Error = Error;

    fn buffer(&mut self) -> SendBuffer<'_> {
        SendBuffer::new(&mut self.send_buffer)
    }

    async fn send_all(&mut self) -> Result<(), Self::Error> {
        self.stream.write_all_buf(&mut self.send_buffer).await?;
        self.stream.flush().await?;
        Ok(())
    }

    async fn shutdown(&mut self) -> Result<(), Self::Error> {
        self.stream.write_all_buf(&mut self.send_buffer).await?;
        self.stream.shutdown().await?;
        Ok(())
    }
}

#[async_trait]
impl<SubStream, Buffer> StreamRecv for RecvStream<SubStream, Buffer>
where
    SubStream: AsyncReadExt + Send + Unpin,
    Buffer: BorrowMut<BytesMut> + Send,
{
    type Error = Error;

    async fn recv(&mut self) -> Result<usize, Self::Error> {
        self.recv_or_eof()
            .await?
            .ok_or_else(|| Error::from(ErrorKind::UnexpectedEof))
    }

    async fn recv_or_eof(&mut self) -> Result<Option<usize>, Self::Error> {
        let size = self.stream.read_buf(self.buffer.borrow_mut()).await?;
        if size == 0 {
            Ok(None)
        } else {
            Ok(Some(size))
        }
    }

    fn buffer(&mut self) -> &mut BytesMut {
        self.buffer.borrow_mut()
    }
}

#[async_trait]
impl<SubStream, Buffer> StreamSend for SendStream<SubStream, Buffer>
where
    SubStream: AsyncWriteExt + Send + Unpin,
    Buffer: BorrowMut<BytesMut> + Send,
{
    type Error = Error;

    fn buffer(&mut self) -> SendBuffer<'_> {
        SendBuffer::new(self.buffer.borrow_mut())
    }

    async fn send_all(&mut self) -> Result<(), Self::Error> {
        self.stream.write_all_buf(self.buffer.borrow_mut()).await?;
        self.stream.flush().await?;
        Ok(())
    }

    async fn shutdown(&mut self) -> Result<(), Self::Error> {
        self.stream.write_all_buf(self.buffer.borrow_mut()).await?;
        self.stream.shutdown().await?;
        Ok(())
    }
}

#[cfg(any(test, feature = "test_harness"))]
mod mock {
    use bytes::BytesMut;
    use tokio::io::{self, DuplexStream};

    use super::{RecvStream, SendStream, Stream};

    impl Stream<DuplexStream> {
        pub fn new_mock(max_buf_size: usize) -> (Self, DuplexStream) {
            let (stream, mock) = io::duplex(max_buf_size);
            (Self::new(stream), mock)
        }
    }

    impl RecvStream<DuplexStream, BytesMut> {
        pub fn new_mock(max_buf_size: usize) -> (Self, DuplexStream) {
            let (stream, mock) = io::duplex(max_buf_size);
            (Self::new(stream, BytesMut::new()), mock)
        }
    }

    impl SendStream<DuplexStream, BytesMut> {
        pub fn new_mock(max_buf_size: usize) -> (Self, DuplexStream) {
            let (stream, mock) = io::duplex(max_buf_size);
            (Self::new(stream, BytesMut::new()), mock)
        }
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use bytes::BufMut;
    use tokio::io::DuplexStream;

    use super::*;

    #[tokio::test]
    async fn stream_recv() {
        test_stream_recv(Stream::new_mock(4096)).await;
        test_stream_recv(RecvStream::new_mock(4096)).await;
    }

    async fn test_stream_recv<Stream>((mut stream, mut mock): (Stream, DuplexStream))
    where
        Stream: StreamRecv<Error = Error> + Send + Unpin,
    {
        assert_eq!(stream.buffer().as_ref(), b"");

        assert_matches!(stream.recv_fill(0).await, Ok(()));
        assert_eq!(stream.buffer().as_ref(), b"");

        mock.write_all(b"hello").await.unwrap();
        assert_matches!(stream.recv().await, Ok(5));
        assert_eq!(stream.buffer().as_ref(), b"hello");

        mock.write_all(b" ").await.unwrap();
        assert_matches!(stream.recv_or_eof().await, Ok(Some(1)));
        assert_eq!(stream.buffer().as_ref(), b"hello ");

        mock.write_all(b"world").await.unwrap();
        assert_matches!(stream.recv_fill(11).await, Ok(()));
        assert_eq!(stream.buffer().as_ref(), b"hello world");

        drop(mock);

        assert_matches!(stream.recv().await, Err(e) if e.kind() == ErrorKind::UnexpectedEof);
        assert_matches!(stream.recv_or_eof().await, Ok(None));
        assert_matches!(stream.recv_fill(11).await, Ok(()));
        assert_matches!(
            stream.recv_fill(12).await,
            Err(e) if e.kind() == ErrorKind::UnexpectedEof,
        );
        assert_eq!(stream.buffer().as_ref(), b"hello world");
    }

    #[tokio::test]
    async fn stream_send() {
        test_stream_send(Stream::new_mock(4096)).await;
        test_stream_send(SendStream::new_mock(4096)).await;
    }

    async fn test_stream_send<Stream>((mut stream, mut mock): (Stream, DuplexStream))
    where
        Stream: StreamSend<Error = Error> + Send + Unpin,
    {
        assert_eq!(stream.buffer().as_ref(), b"".as_slice());

        stream.buffer().put_slice(b"hello world");
        assert_eq!(stream.buffer().as_ref(), b"hello world".as_slice());

        assert_matches!(stream.send_all().await, Ok(()));
        assert_eq!(stream.buffer().as_ref(), b"".as_slice());

        let mut buffer = BytesMut::new();
        mock.read_buf(&mut buffer).await.unwrap();
        assert_eq!(buffer.as_ref(), b"hello world");

        drop(mock);

        assert_matches!(stream.send_all().await, Ok(()));

        stream.buffer().put_slice(b"x");
        assert_matches!(stream.send_all().await, Err(e) if e.kind() == ErrorKind::BrokenPipe);
    }
}
