use std::io::Error;
use std::net::{SocketAddr, SocketAddrV4};

use g1_tokio::net;

pub(crate) async fn lookup_host_first(endpoint: &str) -> Result<SocketAddrV4, Error> {
    match net::lookup_host_first(endpoint).await? {
        SocketAddr::V4(endpoint) => Ok(endpoint),
        SocketAddr::V6(endpoint) => Err(Error::other(format!("ipv6 is not supported: {endpoint}"))),
    }
}
