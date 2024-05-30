#![feature(result_flattening)]

mod actors;
mod init;
mod integrate;
mod storage;

use std::net::SocketAddr;
use std::time::Duration;

use bytes::Bytes;

use bittorrent_metainfo::{InfoOwner, MetainfoOwner};

pub use crate::actors::Actors;
pub use crate::storage::StorageOpen;

g1_param::define!(self_endpoint_ipv4: Option<SocketAddr> = Some("0.0.0.0:6881".parse().unwrap()));
g1_param::define!(self_endpoint_ipv6: Option<SocketAddr> = None); // TODO: Enable IPv6.

g1_param::define!(tcp_listen_backlog: u32 = 256);

g1_param::define!(
    fetch_info_timeout: Duration = Duration::from_secs(60);
    parse = g1_param::parse::duration;
);

g1_param::define!(
    dht_lookup_peers_period: Duration = Duration::from_secs(600);
    parse = g1_param::parse::duration;
);

// Useful for testing.
g1_param::define!(peer_endpoints: Vec<SocketAddr> = Vec::new());

#[derive(Debug)]
pub enum Mode {
    Tracker(MetainfoOwner<Bytes>),
    Trackerless(Option<InfoOwner<Bytes>>),
}
