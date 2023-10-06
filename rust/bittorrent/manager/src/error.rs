use std::io;

use snafu::prelude::*;

use crate::Transport;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Error {
    #[snafu(display("peer manager is cancelled"))]
    Cancelled,
    #[snafu(display("peer manager shutdown grace period is exceeded"))]
    ShutdownGracePeriodExceeded,

    #[snafu(display("utp is not enabled"))]
    UtpNotEnabled,

    #[snafu(display("peer socket connect error"))]
    ConnectError,
    #[snafu(display("peer socket connect timeout: {transport:?}"))]
    ConnectTimeout { transport: Transport },
}

impl From<Error> for io::Error {
    fn from(error: Error) -> Self {
        match error {
            Error::Cancelled => io::Error::other(error),
            Error::ShutdownGracePeriodExceeded => io::Error::new(io::ErrorKind::TimedOut, error),
            Error::UtpNotEnabled => io::Error::other(error),
            Error::ConnectError => io::Error::new(io::ErrorKind::ConnectionRefused, error),
            Error::ConnectTimeout { .. } => io::Error::new(io::ErrorKind::TimedOut, error),
        }
    }
}
