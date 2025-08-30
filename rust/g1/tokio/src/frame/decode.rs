use std::io::{Error, ErrorKind};
use std::pin::Pin;
use std::task::{self, Context, Poll};

use bytes::{BufMut, BytesMut};
use futures::stream::Stream;
use tokio::io::{AsyncRead, ReadBuf};

#[derive(Debug)]
pub struct FrameStream<I, F> {
    input: I,
    decode: F,
    buffer: BytesMut,
}

pub trait Decode {
    type Frame;
    type Error: From<Error>;

    fn decode(&mut self, buffer: &mut BytesMut) -> Result<Option<Self::Frame>, Self::Error>;
}

impl<F, T, E> Decode for F
where
    F: FnMut(&mut BytesMut) -> Result<Option<T>, E>,
    E: From<Error>,
{
    type Frame = T;
    type Error = E;

    fn decode(&mut self, buffer: &mut BytesMut) -> Result<Option<Self::Frame>, Self::Error> {
        self(buffer)
    }
}

impl<I, F> FrameStream<I, F> {
    pub fn new(input: I, decode: F) -> Self {
        Self {
            input,
            decode,
            buffer: BytesMut::new(),
        }
    }

    pub fn with_capacity(input: I, decode: F, capacity: usize) -> Self {
        Self {
            input,
            decode,
            buffer: BytesMut::with_capacity(capacity),
        }
    }
}

// TODO: Can we prove that this is safe?
impl<I, F> Unpin for FrameStream<I, F> {}

impl<I, F> Stream for FrameStream<I, F>
where
    I: AsyncRead,
    F: Decode,
{
    type Item = Result<F::Frame, F::Error>;

    fn poll_next(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        const BUF_SIZE: usize = 4096;
        const MIN_BUF_SIZE: usize = 512;

        let this = self.get_mut();
        loop {
            match this.decode.decode(&mut this.buffer) {
                Ok(Some(frame)) => return Poll::Ready(Some(Ok(frame))),
                Ok(None) => {}
                // TODO: What should we do with the remaining data in `buffer`?
                Err(error) => return Poll::Ready(Some(Err(error))),
            }

            if this.buffer.capacity() - this.buffer.len() < MIN_BUF_SIZE {
                this.buffer.reserve(BUF_SIZE);
            }

            let buf = unsafe { this.buffer.chunk_mut().as_uninit_slice_mut() };
            let mut buf = ReadBuf::uninit(buf);
            let buf_ptr = buf.filled().as_ptr();

            // TODO: Can we prove that this is safe?
            let input = unsafe { Pin::new_unchecked(&mut this.input) };

            let result = task::ready!(input.poll_read(cx, &mut buf));
            assert_eq!(buf_ptr, buf.filled().as_ptr(), "read buf was swapped");

            // TODO: What should we do with the remaining data in `buffer`?
            if let Err(error) = result {
                return Poll::Ready(Some(Err(error.into())));
            }

            let n = buf.filled().len();
            if n == 0 {
                return Poll::Ready(if this.buffer.is_empty() {
                    None
                } else {
                    Some(Err(
                        Error::new(ErrorKind::UnexpectedEof, "partial frame").into()
                    ))
                });
            }
            unsafe { this.buffer.advance_mut(n) };
        }
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::task::Waker;

    use bytes::{Buf, Bytes};
    use futures::stream::StreamExt;
    use tokio::io::{self, AsyncWriteExt};

    use super::*;

    struct TestDecode;

    impl Decode for TestDecode {
        type Frame = Bytes;
        type Error = Error;

        fn decode(&mut self, buffer: &mut BytesMut) -> Result<Option<Self::Frame>, Self::Error> {
            if buffer.is_empty() {
                return Ok(None);
            }

            let len = usize::from(buffer[0]);
            if buffer.len() < 1 + len {
                return Ok(None);
            }

            let _ = buffer.get_u8();
            Ok(Some(buffer.copy_to_bytes(len)))
        }
    }

    #[tokio::test]
    async fn decode() {
        let (mock_r, mut mock_w) = io::simplex(32);
        let mut stream = FrameStream::new(mock_r, TestDecode);

        assert_matches!(mock_w.write_all(b"\x0dHello, World!").await, Ok(()));
        assert_matches!(stream.next().await, Some(Ok(frame)) if frame == b"Hello, World!" as &[u8]);

        assert_matches!(mock_w.write_all(b"\x08spam egg").await, Ok(()));
        assert_matches!(stream.next().await, Some(Ok(frame)) if frame == b"spam egg" as &[u8]);

        assert_matches!(mock_w.shutdown().await, Ok(()));
        assert_matches!(stream.next().await, None);
    }

    #[tokio::test]
    async fn partial_frame() {
        let (mock_r, mut mock_w) = io::simplex(32);
        let mut stream = FrameStream::new(mock_r, TestDecode);

        assert_matches!(mock_w.write_all(b"\x0dHello, ").await, Ok(()));
        assert_matches!(mock_w.shutdown().await, Ok(()));
        assert_matches!(
            stream.next().await,
            Some(Err(error))
            if error.kind() == ErrorKind::UnexpectedEof && error.to_string() == "partial frame",
        );
    }

    // I am not sure how to test this properly, but `FrameStream` should not over-reserve buffer
    // capacity.
    #[tokio::test]
    async fn buffer_capacity() {
        const TESTDATA: &[u8] = b"abcdefghijklmnopqrstuvwxyz0123456789";

        let (mock_r, mut mock_w) = io::simplex(32);
        let mut stream = FrameStream::new(mock_r, TestDecode);

        let mut cx = Context::from_waker(Waker::noop());

        for _ in 0..100 {
            assert_matches!(
                mock_w.write_u8(TESTDATA.len().try_into().unwrap()).await,
                Ok(()),
            );
            assert_matches!(Pin::new(&mut stream).poll_next(&mut cx), Poll::Pending);

            for i in 0..TESTDATA.len() - 1 {
                assert_matches!(mock_w.write_u8(TESTDATA[i]).await, Ok(()));
                assert_matches!(Pin::new(&mut stream).poll_next(&mut cx), Poll::Pending);
            }

            assert_matches!(mock_w.write_u8(TESTDATA[TESTDATA.len() - 1]).await, Ok(()));
            assert_matches!(
                Pin::new(&mut stream).poll_next(&mut cx),
                Poll::Ready(Some(Ok(frame))) if frame == TESTDATA,
            );

            assert!(stream.buffer.capacity() < 5000);
        }
    }
}
