use snafu::prelude::*;

use g1_zmq::envelope::{Envelope, Frame, Multipart};

#[derive(Debug, Snafu)]
pub enum Error {
    #[snafu(display("expect exactly one data frame: {envelope:?}"))]
    ExpectOneDataFrame { envelope: Envelope },
    #[snafu(display("invalid frame sequence: {frames:?}"))]
    InvalidFrameSequence { frames: Multipart },
}

pub fn decode(frames: Multipart) -> Result<Envelope<Frame>, Error> {
    Envelope::try_from(frames).map_err(|frames| match Envelope::try_from(frames) {
        Ok(envelope) => Error::ExpectOneDataFrame { envelope },
        Err(frames) => Error::InvalidFrameSequence { frames },
    })
}
