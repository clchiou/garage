use std::io::{self, ErrorKind};

use snafu::prelude::*;

use bittorrent_base::{InfoHash, PeerId};

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    #[snafu(display("expect info hash == {expect:?}: {info_hash:?}"))]
    ExpectInfoHash {
        info_hash: InfoHash,
        expect: InfoHash,
    },
    #[snafu(display("expect peer id == {expect:?}: {peer_id:?}"))]
    ExpectPeerId { peer_id: PeerId, expect: PeerId },
    #[snafu(display("expect protocol id == {expect}: {protocol_id}"))]
    ExpectProtocolId { protocol_id: String, expect: String },
    #[snafu(display("expect protocol id size == {expect}: {size}"))]
    ExpectProtocolIdSize { size: usize, expect: usize },
    #[snafu(display("handshake timeout"))]
    HandshakeTimeout,

    #[snafu(display("expect message {id} size == {expect}: {size}"))]
    ExpectSizeEqual { id: u8, size: u32, expect: u32 },
    #[snafu(display("expect message {id} size >= {expect}: {size}"))]
    ExpectSizeGreaterOrEqual { id: u8, size: u32, expect: u32 },
    #[snafu(display("expect message size <= {limit}: {size}"))]
    SizeExceededLimit { size: u32, limit: usize },
    #[snafu(display("unknown id: {id}"))]
    UnknownId { id: u8 },
}

impl From<Error> for io::Error {
    fn from(error: Error) -> Self {
        match error {
            Error::HandshakeTimeout => Self::new(ErrorKind::TimedOut, error),
            _ => Self::other(error),
        }
    }
}
