use std::io;

use snafu::prelude::*;

use crate::{Endpoint, Transport};

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Error {
    #[snafu(display("utp is not enabled: {peer_endpoint:?}"))]
    UtpNotEnabled { peer_endpoint: Endpoint },

    #[snafu(display("peer connect timeout: {peer_endpoint:?} {transport:?}"))]
    ConnectTimeout {
        peer_endpoint: Endpoint,
        transport: Transport,
    },
    #[snafu(display("peer unreachable: {peer_endpoint:?}"))]
    Unreachable { peer_endpoint: Endpoint },
}

impl From<Error> for io::Error {
    fn from(error: Error) -> Self {
        io::Error::new(
            match error {
                Error::UtpNotEnabled { .. } => io::ErrorKind::Other,
                Error::ConnectTimeout { .. } => io::ErrorKind::TimedOut,
                Error::Unreachable { .. } => io::ErrorKind::ConnectionRefused,
            },
            error,
        )
    }
}
