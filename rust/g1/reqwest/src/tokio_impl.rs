use std::future::Future;
use std::io::Error;
use std::pin::Pin;
use std::task::{self, Context, Poll};

use bytes::Bytes;
use reqwest::Response;
use tokio::io::{AsyncBufRead, AsyncRead, ReadBuf};

use g1_base::fmt::{DebugExt, InsertPlaceholder};

#[derive(DebugExt)]
pub struct Reader {
    response: Pin<Box<Response>>,
    // Invariant: chunk_fut.is_none() || chunk.is_empty()
    #[debug(with = InsertPlaceholder)]
    chunk_fut: Option<ChunkFut>,
    chunk: Bytes,
}

type ChunkFut =
    Pin<Box<dyn Future<Output = Result<Option<Bytes>, reqwest::Error>> + Send + Sync + 'static>>;

impl From<Response> for Reader {
    fn from(response: Response) -> Self {
        Self::new(response)
    }
}

impl From<Reader> for Response {
    fn from(reader: Reader) -> Self {
        reader.into_inner()
    }
}

impl Reader {
    pub fn new(response: Response) -> Self {
        Self {
            response: Box::pin(response),
            chunk_fut: None,
            chunk: Bytes::new(),
        }
    }

    // NOTE: This drops the active `chunk_fut` future, effectively canceling it.
    pub fn into_inner(self) -> Response {
        let Self { response, .. } = self;
        Box::into_inner(Pin::into_inner(response))
    }

    fn poll_chunk(&mut self, cx: &mut Context<'_>) -> Poll<Result<(), Error>> {
        if !self.chunk.is_empty() {
            assert!(self.chunk_fut.is_none());
            return Poll::Ready(Ok(()));
        }

        let chunk_fut = self.chunk_fut.get_or_insert_with(|| {
            // TODO: Can we prove that this is actually safe?
            let response = unsafe { &mut *(self.response.as_mut().get_mut() as *mut Response) };
            Box::pin(response.chunk())
        });
        let result = task::ready!(chunk_fut.as_mut().poll(cx));
        self.chunk_fut = None;

        Poll::Ready(match result {
            Ok(chunk) => {
                self.chunk = chunk.unwrap_or_else(Bytes::new);
                Ok(())
            }
            Err(error) => Err(Error::other(error)),
        })
    }

    fn consume_chunk(&mut self, amt: usize) -> Bytes {
        self.chunk.split_to(amt.min(self.chunk.len()))
    }
}

impl AsyncRead for Reader {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &mut ReadBuf<'_>,
    ) -> Poll<Result<(), Error>> {
        let this = self.get_mut();
        task::ready!(this.poll_chunk(cx))?;
        buf.put_slice(&this.consume_chunk(buf.remaining()));
        Poll::Ready(Ok(()))
    }
}

impl AsyncBufRead for Reader {
    fn poll_fill_buf(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Result<&[u8], Error>> {
        let this = self.get_mut();
        task::ready!(this.poll_chunk(cx))?;
        Poll::Ready(Ok(&this.chunk))
    }

    fn consume(self: Pin<&mut Self>, amt: usize) {
        let _: Bytes = self.get_mut().consume_chunk(amt);
    }
}
