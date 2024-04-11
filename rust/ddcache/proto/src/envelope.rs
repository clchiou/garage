use capnp::message::{self, Allocator};
use capnp::serialize;
use snafu::prelude::*;

use g1_zmq::envelope::{Envelope, Frame, Multipart};

use crate::{RequestOwner, ResponseOwner, ResponseResult, ResponseResultOwner};

#[derive(Debug, Snafu)]
pub enum Error {
    #[snafu(display("decode error: {envelope:?}"))]
    Decode { envelope: Envelope<capnp::Error> },
    #[snafu(display("expect exactly one data frame: {envelope:?}"))]
    ExpectOneDataFrame { envelope: Envelope },
    #[snafu(display("invalid frame sequence: {frames:?}"))]
    InvalidFrameSequence { frames: Multipart },
}

pub fn decode_request(frames: Multipart) -> Result<Envelope<RequestOwner>, Error> {
    decode(frames)?
        .map(RequestOwner::try_from)
        .unzip()
        .map_err(|envelope| Error::Decode { envelope })
}

pub fn decode(frames: Multipart) -> Result<Envelope<Frame>, Error> {
    Envelope::try_from(frames).map_err(|frames| match Envelope::try_from(frames) {
        Ok(envelope) => Error::ExpectOneDataFrame { envelope },
        Err(frames) => Error::InvalidFrameSequence { frames },
    })
}

pub fn decode_response(
    response: Envelope<Frame>,
) -> Result<Envelope<ResponseResultOwner>, capnp::Error> {
    response
        .map(ResponseOwner::try_from)
        .transpose()?
        .map(|data| {
            // It is safe to `transpose` because `E` is `capnp::Error`.
            unsafe { data.map(ResponseResult::try_from).transpose() }
        })
        .transpose()
}

pub fn encode<A>(envelope: Envelope<message::Builder<A>>) -> Envelope<Frame>
where
    A: Allocator,
{
    envelope.map(|data| serialize::write_message_to_words(&data).into())
}
