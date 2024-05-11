use snafu::prelude::*;

#[derive(Debug, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    #[snafu(display("not connected to any shard"))]
    NotConnected,
    #[snafu(display("protocol error: {source}"))]
    Protocol { source: ddcache_client_raw::Error },
}
