use snafu::prelude::*;

use ddcache_rpc::Endpoint;

#[derive(Debug, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    #[snafu(display("disconnected: {endpoint}"))]
    Disconnected { endpoint: Endpoint },
    #[snafu(display("not connected to any shard"))]
    NotConnected,
    #[snafu(display("protocol error: {source}"))]
    Protocol { source: ddcache_client_raw::Error },
    #[snafu(display("client connector task stopped"))]
    Stopped,
}
