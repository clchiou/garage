use std::io;

use snafu::prelude::*;

use crate::handshake::PADDING_SIZE_RANGE;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(visibility(pub(super)))]
pub enum Error {
    #[snafu(display("expect crypto_provide & {expect} != 0: {crypto_provide}"))]
    ExpectCryptoProvide {
        crypto_provide: u32,
        expect: u32,
    },
    #[snafu(display("expect crypto_select & {expect} != 0: {crypto_select}"))]
    ExpectCryptoSelect {
        crypto_select: u32,
        expect: u32,
    },
    #[snafu(display("expect padding size in {PADDING_SIZE_RANGE:?}: {size}"))]
    ExpectPaddingSize {
        size: usize,
    },
    #[snafu(display("expect payload size <= {expect}: {size}"))]
    ExpectPayloadSize {
        size: usize,
        expect: usize,
    },
    #[snafu(display("expect recv {name} == {expect:?}: {actual:?}"))]
    ExpectRecv {
        name: &'static str,
        actual: Vec<u8>,
        expect: Vec<u8>,
    },
    #[snafu(display("expect recv public key size <= dh_key + padding: {size}"))]
    ExpectRecvPublicKeySize {
        size: usize,
    },
    #[snafu(display("expect resynchronize window size <= {expect}: {size}"))]
    ExpectResynchronize {
        size: usize,
        expect: usize,
    },
    RecvPublicKeyTimeout,
    Timeout,
}

impl From<Error> for io::Error {
    fn from(error: Error) -> Self {
        match error {
            Error::ExpectCryptoProvide { .. }
            | Error::ExpectCryptoSelect { .. }
            | Error::ExpectPaddingSize { .. }
            | Error::ExpectPayloadSize { .. }
            | Error::ExpectRecv { .. }
            | Error::ExpectRecvPublicKeySize { .. }
            | Error::ExpectResynchronize { .. } => {
                io::Error::new(io::ErrorKind::ConnectionAborted, error)
            }
            Error::RecvPublicKeyTimeout => {
                io::Error::new(io::ErrorKind::TimedOut, "mse recv public key timeout")
            }
            Error::Timeout => io::Error::new(io::ErrorKind::TimedOut, "mse handshake timeout"),
        }
    }
}
