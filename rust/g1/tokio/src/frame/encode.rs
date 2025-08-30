use std::io::{Error, ErrorKind};
use std::pin::Pin;
use std::task::{self, Context, Poll};

use bytes::{Buf, BytesMut};
use futures::sink::Sink;
use tokio::io::AsyncWrite;

#[derive(Debug)]
pub struct FrameSink<O, F> {
    output: O,
    encode: F,
    buffer: BytesMut,
}

pub trait Encode<Frame> {
    type Error: From<Error>;

    fn encode(&mut self, frame: Frame, buffer: &mut BytesMut) -> Result<(), Self::Error>;
}

impl<F, T, E> Encode<T> for F
where
    F: FnMut(T, &mut BytesMut) -> Result<(), E>,
    E: From<Error>,
{
    type Error = E;

    fn encode(&mut self, frame: T, buffer: &mut BytesMut) -> Result<(), Self::Error> {
        self(frame, buffer)
    }
}

impl<O, F> FrameSink<O, F> {
    pub fn new(output: O, encode: F) -> Self {
        Self {
            output,
            encode,
            buffer: BytesMut::new(),
        }
    }

    pub fn with_capacity(output: O, encode: F, capacity: usize) -> Self {
        Self {
            output,
            encode,
            buffer: BytesMut::with_capacity(capacity),
        }
    }
}

// TODO: Can we prove that this is safe?
impl<O, F> Unpin for FrameSink<O, F> {}

impl<O, F, Frame> Sink<Frame> for FrameSink<O, F>
where
    O: AsyncWrite,
    F: Encode<Frame>,
{
    type Error = F::Error;

    fn poll_ready(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        const WRITE_BUF_SIZE: usize = 4096;

        if self.buffer.len() < WRITE_BUF_SIZE {
            Poll::Ready(Ok(()))
        } else {
            self.poll_flush(cx)
        }
    }

    fn start_send(self: Pin<&mut Self>, frame: Frame) -> Result<(), Self::Error> {
        let this = self.get_mut();
        this.encode.encode(frame, &mut this.buffer)
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        let this = self.get_mut();

        // TODO: Can we prove that this is safe?
        let mut output = unsafe { Pin::new_unchecked(&mut this.output) };

        while !this.buffer.is_empty() {
            let n = task::ready!(output.as_mut().poll_write(cx, this.buffer.chunk()))?;
            if n == 0 {
                // TODO: What should we do with the remaining data in `buffer`?
                return Poll::Ready(Err(
                    Error::new(ErrorKind::UnexpectedEof, "partial write").into()
                ));
            }
            this.buffer.advance(n);
        }

        task::ready!(output.poll_flush(cx))?;

        Poll::Ready(Ok(()))
    }

    fn poll_close(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        task::ready!(self.as_mut().poll_flush(cx))?;

        // TODO: Can we prove that this is safe?
        let output = unsafe { self.map_unchecked_mut(|this| &mut this.output) };
        task::ready!(output.poll_shutdown(cx))?;

        Poll::Ready(Ok(()))
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use bytes::{BufMut, Bytes};
    use futures::sink::SinkExt;
    use tokio::io::{self, AsyncReadExt};

    use super::*;

    struct TestEncode;

    impl Encode<Bytes> for TestEncode {
        type Error = Error;

        fn encode(&mut self, frame: Bytes, buffer: &mut BytesMut) -> Result<(), Self::Error> {
            buffer.put_u8(frame.len().try_into().unwrap());
            buffer.put_slice(&frame);
            Ok(())
        }
    }

    #[tokio::test]
    async fn encode() {
        let (mut mock_r, mock_w) = io::simplex(32);
        let mut sink = FrameSink::new(mock_w, TestEncode);

        let mut output = BytesMut::new();
        assert_matches!(
            sink.send(Bytes::from_static(b"Hello, World!")).await,
            Ok(())
        );
        assert_matches!(sink.flush().await, Ok(()));
        assert_matches!(mock_r.read_buf(&mut output).await, Ok(14));
        assert_eq!(output, b"\x0dHello, World!" as &[u8]);

        output.clear();
        assert_matches!(sink.send(Bytes::from_static(b"spam egg")).await, Ok(()));
        assert_matches!(sink.flush().await, Ok(()));
        assert_matches!(mock_r.read_buf(&mut output).await, Ok(9));
        assert_eq!(output, b"\x08spam egg" as &[u8]);
    }

    // TODO: How do we test the "partial write" error?
}
