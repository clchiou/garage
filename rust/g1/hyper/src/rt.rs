use std::io::{Error, IoSlice};
use std::pin::Pin;
use std::task::{Context, Poll};

use hyper::rt::{Read, ReadBufCursor, Write};
use tokio::io::{AsyncRead, AsyncWrite, ReadBuf};

use g1_base::task::PollExt;

#[derive(Debug)]
pub struct TokioAdapter<T>(T);

impl<T> TokioAdapter<T> {
    pub fn new(inner: T) -> Self {
        Self(inner)
    }

    pub fn unwrap(self) -> T {
        self.0
    }

    fn project(self: Pin<&mut Self>) -> Pin<&mut T> {
        unsafe { self.map_unchecked_mut(|this| &mut this.0) }
    }
}

impl<T> Read for TokioAdapter<T>
where
    T: AsyncRead,
{
    fn poll_read(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        mut buffer: ReadBufCursor<'_>,
    ) -> Poll<Result<(), Error>> {
        let poll;
        let n = {
            let mut buf = ReadBuf::uninit(unsafe { buffer.as_mut() });
            poll = self.project().poll_read(context, &mut buf);
            buf.filled().len()
        };
        poll.inspect(|result| {
            if matches!(result, Ok(())) {
                unsafe { buffer.advance(n) }
            }
        })
    }
}

impl<T> Write for TokioAdapter<T>
where
    T: AsyncWrite,
{
    fn poll_write(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &[u8],
    ) -> Poll<Result<usize, Error>> {
        self.project().poll_write(context, buffer)
    }

    fn poll_flush(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Result<(), Error>> {
        self.project().poll_flush(context)
    }

    fn poll_shutdown(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Result<(), Error>> {
        self.project().poll_shutdown(context)
    }

    fn is_write_vectored(&self) -> bool {
        self.0.is_write_vectored()
    }

    fn poll_write_vectored(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffers: &[IoSlice<'_>],
    ) -> Poll<Result<usize, Error>> {
        self.project().poll_write_vectored(context, buffers)
    }
}
