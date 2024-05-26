use std::io;

use snafu::prelude::*;

use g1_zmq::envelope::{Envelope, Frame};

use dkvcache_rpc::envelope;

#[derive(Debug, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    #[snafu(display("raw client task stopped"))]
    Stopped,

    #[snafu(display("request error: {source}"))]
    Request { source: io::Error },
    #[snafu(display("request timeout"))]
    RequestTimeout,

    #[snafu(display("decode error: {source}"))]
    Decode { source: capnp::Error },
    #[snafu(display("unexpected response"))]
    UnexpectedResponse,

    #[snafu(display("rpc error: {source}"))]
    Rpc { source: dkvcache_rpc::Error },
}

#[derive(Debug, Snafu)]
#[snafu(visibility(pub(crate)))]
pub(crate) enum ResponseError {
    #[snafu(display("invalid response: {source}"))]
    InvalidResponse { source: envelope::Error },
    #[snafu(display("invalid routing id: {response:?}"))]
    InvalidRoutingId { response: Envelope<Frame> },
}
