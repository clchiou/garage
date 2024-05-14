use snafu::prelude::*;

use ddcache_client_service::NotConnectedError;

#[derive(Debug, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    #[snafu(display("not connected to any shard"))]
    NotConnected,
    #[snafu(display("request error: {source}"))]
    Request { source: ddcache_client_raw::Error },
}

impl From<NotConnectedError> for Error {
    fn from(_: NotConnectedError) -> Self {
        Self::NotConnected
    }
}
