use std::pin::Pin;
use std::task::{Context, Poll};

use async_trait::async_trait;
use bytes::BytesMut;
// We use `futures::stream::Stream` because `std::async_iter::AsyncIterator` (previously known as
// `std::stream::Stream`) is still a bare-bones implementation - it does not even have an
// `async fn next` method!
use futures::{future::BoxFuture, sink, stream};

use g1_base::fmt::{DebugExt, InsertPlaceholder};

use super::{StreamRecv, StreamSend};

#[async_trait]
pub trait Decode<Stream>
where
    Stream: StreamRecv,
{
    type Item;
    type Error: From<Stream::Error>;

    /// Decodes a byte stream and returns a stream item or an error when EOF is reached, but the
    /// byte stream buffer is not empty.
    async fn decode(&mut self, stream: &mut Stream) -> Result<Option<Self::Item>, Self::Error>;
}

pub trait Encode<Item> {
    /// Encodes a stream item and writes the output to a byte stream buffer.
    fn encode(&mut self, item: &Item, buffer: &mut BytesMut);
}

// TODO: We intend to implement `Decode` for async functions, similar to what we do for `Encode`.
// However, for unknown reasons, it is causing the compiler to crash.  Currently, we are only able
// to provide an implementation for non-async functions.
#[async_trait]
impl<Stream, DecodeFn, Item, Error> Decode<Stream> for DecodeFn
where
    Stream: StreamRecv + Send,
    DecodeFn: Fn(&mut BytesMut) -> Result<Option<Item>, Error> + Send,
    Item: Send,
    Error: From<Stream::Error> + Send,
{
    type Item = Item;
    type Error = Error;

    async fn decode(&mut self, stream: &mut Stream) -> Result<Option<Self::Item>, Self::Error> {
        loop {
            if let Some(item) = self(stream.buffer())? {
                return Ok(Some(item));
            }
            if stream.recv_or_eof().await?.is_none() {
                if stream.buffer().is_empty() {
                    return Ok(None);
                } else {
                    // Return the `UnexpectedEof` error raised by the `recv` function.
                    return Err(stream.recv().await.expect_err("expect EOF").into());
                }
            }
        }
    }
}

impl<EncodeFn, Item> Encode<Item> for EncodeFn
where
    EncodeFn: Fn(&Item, &mut BytesMut),
{
    fn encode(&mut self, item: &Item, buffer: &mut BytesMut) {
        self(item, buffer)
    }
}

//
// Implementer's notes: We store future values in `Source` and `Sink`.  These future values have to
// satisfy the `'static` lifetime bound because trait methods like `Stream::poll_next` do not take
// a lifetime parameter on `&mut Self`.  To satisfy this, when producing a future value, we move
// all related values into it, and they will be moved back after it is completed (so that we can
// produce the next future value).
//
// There may be other ways to satisfy the `'static` lifetime bound, but for now, this "move" trick
// is the best I have.
//

/// Byte Stream to `futures::stream::Stream` Adapter
#[derive(DebugExt)]
pub struct Source<Stream, Decoder>
where
    Stream: StreamRecv,
    Decoder: Decode<Stream>,
{
    #[debug(with = InsertPlaceholder)]
    source: Option<(Stream, Decoder)>,
    #[debug(with = InsertPlaceholder)]
    next_future: Option<SourceFuture<Stream, Decoder, Decoder::Item, Decoder::Error>>,
}

/// `futures::sink::Sink` to Byte Stream Adapter
#[derive(DebugExt)]
pub struct Sink<Stream, Encoder>
where
    Stream: StreamSend,
{
    #[debug(with = InsertPlaceholder)]
    stream: Option<Stream>,
    #[debug(with = InsertPlaceholder)]
    encoder: Encoder,
    #[debug(with = InsertPlaceholder)]
    flush_future: Option<SinkFuture<Stream, Stream::Error>>,
    #[debug(with = InsertPlaceholder)]
    close_future: Option<SinkFuture<Stream, Stream::Error>>,
}

// TODO: Use where clauses to simplify these type aliases when rustc starts enforcing where clauses
// in type aliases.  For more details, check [rust-lang/rust#21903][#21903].
//
// [#21903]: https://github.com/rust-lang/rust/issues/21903
type SourceFuture<Stream, Decoder, Item, Error> =
    BoxFuture<'static, SourceOutput<Stream, Decoder, Item, Error>>;
type SourceOutput<Stream, Decoder, Item, Error> = ((Stream, Decoder), Option<Result<Item, Error>>);
type SinkFuture<Stream, Error> = BoxFuture<'static, SinkOutput<Stream, Error>>;
type SinkOutput<Stream, Error> = (Stream, Result<(), Error>);

macro_rules! poll {
    ($this:ident, $get_future:ident, $context:ident $(,)?) => {
        $this
            .$get_future()
            .as_mut()
            .poll($context)
            .map(|(state, result)| {
                $this.reset(state);
                result
            })
    };
}

impl<Stream, Decoder> Source<Stream, Decoder>
where
    Stream: StreamRecv,
    Decoder: Decode<Stream>,
{
    pub fn new(stream: Stream, decoder: Decoder) -> Self {
        Self {
            source: Some((stream, decoder)),
            next_future: None,
        }
    }

    fn reset(&mut self, source: (Stream, Decoder)) {
        self.source = Some(source);
        self.next_future = None;
    }
}

impl<Stream, Decoder> Source<Stream, Decoder>
where
    Stream: StreamRecv + Send + 'static,
    Decoder: Decode<Stream> + Send + 'static,
{
    fn next_future(&mut self) -> &mut SourceFuture<Stream, Decoder, Decoder::Item, Decoder::Error> {
        self.next_future
            .get_or_insert_with(|| Box::pin(Self::next(self.source.take().unwrap())))
    }

    async fn next(
        (mut stream, mut decoder): (Stream, Decoder),
    ) -> SourceOutput<Stream, Decoder, Decoder::Item, Decoder::Error> {
        let result = decoder.decode(&mut stream).await.transpose();
        ((stream, decoder), result)
    }
}

impl<Stream, Decoder> stream::Stream for Source<Stream, Decoder>
where
    Stream: StreamRecv + Send + Unpin + 'static,
    Decoder: Decode<Stream> + Send + Unpin + 'static,
{
    type Item = Result<Decoder::Item, Decoder::Error>;

    fn poll_next(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        let this = self.get_mut();
        poll!(this, next_future, context)
    }
}

impl<Stream, Encoder> Sink<Stream, Encoder>
where
    Stream: StreamSend,
{
    pub fn new(stream: Stream, encoder: Encoder) -> Self {
        Self {
            stream: Some(stream),
            encoder,
            flush_future: None,
            close_future: None,
        }
    }

    fn reset(&mut self, stream: Stream) {
        self.stream = Some(stream);
        self.flush_future = None;
        self.close_future = None;
    }
}

impl<Stream, Encoder> Sink<Stream, Encoder>
where
    Stream: StreamSend + Send + 'static,
    Encoder: 'static,
{
    fn flush_future(&mut self) -> &mut SinkFuture<Stream, Stream::Error> {
        self.flush_future
            .get_or_insert_with(|| Box::pin(Self::flush(self.stream.take().unwrap())))
    }

    async fn flush(mut stream: Stream) -> SinkOutput<Stream, Stream::Error> {
        let result = stream.send_all().await;
        (stream, result)
    }

    fn close_future(&mut self) -> &mut SinkFuture<Stream, Stream::Error> {
        self.close_future
            .get_or_insert_with(|| Box::pin(Self::close(self.stream.take().unwrap())))
    }

    async fn close(mut stream: Stream) -> SinkOutput<Stream, Stream::Error> {
        let result = stream.shutdown().await;
        (stream, result)
    }
}

impl<Stream, Encoder, Item> sink::Sink<Item> for Sink<Stream, Encoder>
where
    Stream: StreamSend + Send + Unpin + 'static,
    Encoder: Encode<Item> + Unpin + 'static,
{
    type Error = Stream::Error;

    fn poll_ready(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        match self.get_mut().stream {
            Some(_) => Poll::Ready(Ok(())),
            None => Poll::Pending,
        }
    }

    fn start_send(self: Pin<&mut Self>, item: Item) -> Result<(), Self::Error> {
        let this = self.get_mut();
        this.encoder
            .encode(&item, &mut this.stream.as_mut().unwrap().buffer());
        Ok(())
    }

    fn poll_flush(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Result<(), Self::Error>> {
        let this = self.get_mut();
        poll!(this, flush_future, context)
    }

    fn poll_close(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Result<(), Self::Error>> {
        let this = self.get_mut();
        poll!(this, close_future, context)
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::io::{Error, ErrorKind};

    use bytes::{Buf, BufMut};
    use futures::{sink::SinkExt, stream::StreamExt};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    use crate::io::{RecvStream, SendStream};

    use super::*;

    fn decode(buffer: &mut BytesMut) -> Result<Option<String>, Error> {
        if buffer.remaining() < 1 {
            return Ok(None);
        }
        let size = usize::from(buffer[0]);
        if buffer.remaining() < 1 + size {
            return Ok(None);
        }
        let mut vec = vec![0u8; size];
        buffer.get_u8();
        buffer.copy_to_slice(&mut vec);
        Ok(Some(String::from_utf8(vec).unwrap()))
    }

    #[tokio::test]
    async fn source() {
        let (stream, mut mock) = RecvStream::new_mock(4096);
        let mut source = Source::new(stream, decode);
        mock.write_all(b"\x0bhello world\x03foo\x03bar")
            .await
            .unwrap();
        drop(mock);
        assert_matches!(source.next().await, Some(Ok(x)) if x == "hello world");
        assert_matches!(source.next().await, Some(Ok(x)) if x == "foo");
        assert_matches!(source.next().await, Some(Ok(x)) if x == "bar");
        assert_matches!(source.next().await, None);
    }

    #[tokio::test]
    async fn source_unexpected_eof() {
        let (stream, mut mock) = RecvStream::new_mock(4096);
        let mut source = Source::new(stream, decode);
        mock.write_all(b"\x0bhello").await.unwrap();
        drop(mock);
        assert_matches!(source.next().await, Some(Err(e)) if e.kind() == ErrorKind::UnexpectedEof);
    }

    fn encode(item: &String, buffer: &mut BytesMut) {
        buffer.put_u8(item.len().try_into().unwrap());
        buffer.put_slice(item.as_bytes());
    }

    #[tokio::test]
    async fn sink() {
        let (stream, mut mock) = SendStream::new_mock(4096);
        let mut sink = Sink::new(stream, encode);

        assert_matches!(sink.feed("hello world".to_string()).await, Ok(()));
        assert_matches!(sink.flush().await, Ok(()));
        let mut buffer = BytesMut::new();
        assert_matches!(mock.read_buf(&mut buffer).await, Ok(12));
        assert_eq!(buffer.as_ref(), b"\x0bhello world");

        assert_matches!(sink.feed("foo".to_string()).await, Ok(()));
        assert_matches!(sink.feed("bar".to_string()).await, Ok(()));
        assert_matches!(sink.close().await, Ok(()));
        buffer.clear();
        assert_matches!(mock.read_buf(&mut buffer).await, Ok(8));
        assert_eq!(buffer.as_ref(), b"\x03foo\x03bar");
    }
}
