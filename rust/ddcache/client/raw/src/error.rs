use std::io;

use snafu::prelude::*;

use g1_zmq::envelope::{Envelope, Frame};

use ddcache_rpc::envelope;
use ddcache_rpc::rpc_capnp::error;

#[derive(Debug, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    #[snafu(display("raw client task stopped"))]
    Stopped,

    //
    // Network or server errors.
    //
    #[snafu(display("request error: {source}"))]
    Request { source: io::Error },
    #[snafu(display("request timeout"))]
    RequestTimeout,

    //
    // Decode response errors.
    //
    #[snafu(display("decode error: {source}"))]
    Decode { source: capnp::Error },
    #[snafu(display("unexpected response"))]
    UnexpectedResponse,

    //
    // Protocol errors.
    //
    #[snafu(display("server error"))]
    Server,
    #[snafu(display("server unavailable"))]
    Unavailable,

    #[snafu(display("invalid request"))]
    InvalidRequest,
    #[snafu(display("expect key size <= {max}"))]
    MaxKeySizeExceeded { max: u32 },
    #[snafu(display("expect metadata size <= {max}"))]
    MaxMetadataSizeExceeded { max: u32 },
    #[snafu(display("expect blob size <= {max}"))]
    MaxBlobSizeExceeded { max: u32 },

    //
    // Blob I/O error.
    //
    #[snafu(display("blob request timeout"))]
    BlobRequestTimeout,
    #[snafu(display("blob io error: {source}"))]
    Io { source: io::Error },
    #[snafu(display("expect read/write {expect} bytes: {size}"))]
    PartialIo { size: usize, expect: usize },
}

impl TryFrom<error::Reader<'_>> for Error {
    type Error = capnp::Error;

    fn try_from(error: error::Reader<'_>) -> Result<Self, Self::Error> {
        Ok(match error.which()? {
            error::Server(()) => Error::Server,
            error::Unavailable(()) => Error::Unavailable,
            error::InvalidRequest(()) => Error::InvalidRequest,
            error::MaxKeySizeExceeded(max) => Error::MaxKeySizeExceeded { max },
            error::MaxMetadataSizeExceeded(max) => Error::MaxMetadataSizeExceeded { max },
            error::MaxBlobSizeExceeded(max) => Error::MaxBlobSizeExceeded { max },
        })
    }
}

#[derive(Debug, Snafu)]
#[snafu(visibility(pub(crate)))]
pub(crate) enum ResponseError {
    #[snafu(display("invalid response: {source}"))]
    InvalidResponse { source: envelope::Error },
    #[snafu(display("invalid routing id: {response:?}"))]
    InvalidRoutingId { response: Envelope<Frame> },
}
