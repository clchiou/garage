//! Byte Stream
//!
//! A stream is composed of a buffer and a sub-stream.  When sending data, a user writes data to
//! the buffer and then flushes the buffer's data to the sub-stream.  When receiving data, the
//! sub-stream fills the buffer, and then the user reads data from the buffer.
//!
//! NOTE: We have chosen to make the stream traits expose `bytes::BytesMut` as the buffer type
//! instead of exposing `bytes::Buf` and `bytes::BufMut`.  This decision makes it easier to add
//! transformations on top of a stream.
//!
//! NOTE: We have not given too much thought to the issue of `async_trait` vs
//! `feature(async_fn_in_traits)`.  For now, `async_trait` is picked arbitrarily.

pub mod transform;

use std::ops::DerefMut;

use async_trait::async_trait;
use bytes::{Buf, BytesMut};

#[async_trait]
pub trait StreamRecv {
    type Buffer<'a>: DerefMut<Target = BytesMut>
    where
        Self: 'a;
    type Error;

    /// Receives data from the sub-stream, returning the size of the received data or an error when
    /// EOF is reached.
    async fn recv(&mut self) -> Result<usize, Self::Error>;

    /// Receives data from the sub-stream, returning the size of the received data or `None` when
    /// EOF is reached.
    async fn recv_or_eof(&mut self) -> Result<Option<usize>, Self::Error>;

    /// Receives data from the sub-stream until the buffer size is greater than or equal to
    /// `min_size`.
    ///
    /// If the buffer size is already greater than or equal to `min_size`, it returns immediately
    /// without receiving data from the sub-stream.  It returns an error when EOF is reached and
    /// the buffer size is less than `min_size`.
    async fn recv_fill(&mut self, min_size: usize) -> Result<(), Self::Error> {
        while self.buffer().remaining() < min_size {
            self.recv().await?;
        }
        Ok(())
    }

    /// Returns the buffer of the stream.
    fn buffer(&mut self) -> Self::Buffer<'_>;
}

#[async_trait]
pub trait StreamSend {
    type Buffer<'a>: DerefMut<Target = BytesMut>
    where
        Self: 'a;
    type Error;

    /// Returns the buffer of the stream.
    fn buffer(&mut self) -> Self::Buffer<'_>;

    /// Sends all buffer data to the sub-stream.
    ///
    /// If the sub-stream is buffered, it also flushes the sub-stream's buffer.
    async fn send_all(&mut self) -> Result<(), Self::Error>;

    /// Sends all buffer data to the sub-stream and then shuts it down.
    async fn shutdown(&mut self) -> Result<(), Self::Error>;
}

/// Helper trait that resolves method name conflicts among the super-traits.
pub trait StreamBuffer: StreamRecv + StreamSend {
    /// Returns the send buffer of the stream.
    fn recv_buffer(&mut self) -> <Self as StreamRecv>::Buffer<'_> {
        StreamRecv::buffer(self)
    }

    /// Returns the recv buffer of the stream.
    fn send_buffer(&mut self) -> <Self as StreamSend>::Buffer<'_> {
        StreamSend::buffer(self)
    }
}

impl<T> StreamBuffer for T where T: StreamRecv + StreamSend {}

pub trait StreamSplit {
    type RecvHalf<'a>: StreamRecv
    where
        Self: 'a;
    type SendHalf<'a>: StreamSend
    where
        Self: 'a;

    /// Splits the stream into a receive half and a send half, both of which can be used
    /// concurrently and mutably borrow from the stream.
    fn split(&mut self) -> (Self::RecvHalf<'_>, Self::SendHalf<'_>);
}

pub trait StreamIntoSplit {
    type OwnedRecvHalf: StreamRecv;
    type OwnedSendHalf: StreamSend;

    /// Splits the stream into a receive half and a send half, both of which can be used
    /// concurrently and are self-owned.
    fn into_split(self) -> (Self::OwnedRecvHalf, Self::OwnedSendHalf);

    /// Puts the two halves back together and recovers the original stream, or errs if the two
    /// halves did not originate from the same stream.
    fn reunite(
        recv: Self::OwnedRecvHalf,
        send: Self::OwnedSendHalf,
    ) -> Result<Self, (Self::OwnedRecvHalf, Self::OwnedSendHalf)>
    where
        Self: Sized;
}
