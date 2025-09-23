use std::io::{self, ErrorKind};

use snafu::prelude::*;

use bt_proto::message;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("message broadcast channel blocked"))]
pub struct Error;

impl From<Error> for io::Error {
    fn from(error: Error) -> Self {
        Self::new(ErrorKind::TimedOut, error)
    }
}

// We have two error paths.  One path goes to the broadcast receivers (network I/O error or message
// error), and the other goes to the actor result.
#[derive(Debug, Snafu)]
#[snafu(visibility(pub(crate)))]
pub(crate) enum ConnActorError {
    #[snafu(display("backlog full"))]
    Backlog,
    #[snafu(display("io error: {source}"))]
    Io { source: io::Error },
    #[snafu(display("message error: {source}"))]
    Message { source: message::Error },

    #[snafu(display("{source}"))]
    Broadcast { source: Error },
}

impl ConnActorError {
    pub(crate) fn into_broadcast(self) -> Result<io::Error, Error> {
        match self {
            Self::Backlog => Ok(io::Error::other(self)),
            Self::Io { source } => Ok(source),
            Self::Message { source } => Ok(source.into()),
            // If the broadcast channel is blocked, it is pointless to send additional messages.
            Self::Broadcast { source } => Err(source),
        }
    }
}
