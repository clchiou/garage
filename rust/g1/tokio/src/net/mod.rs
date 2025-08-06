#[cfg(feature = "icmp")]
pub mod icmp;
pub mod tcp;

use std::io::Error;
use std::net::SocketAddr;

use tokio::net::{self, ToSocketAddrs};

pub async fn lookup_host_first<T>(endpoint: T) -> Result<SocketAddr, Error>
where
    T: ToSocketAddrs,
{
    net::lookup_host(endpoint)
        .await?
        .next()
        .ok_or_else(|| Error::other("cannot be resolved to any addresses"))
}
