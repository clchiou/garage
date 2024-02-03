mod agents;
mod net;
mod storage;
mod task;

use std::net::SocketAddr;
use std::time::Duration;

pub use crate::agents::{Agents, Mode};
pub use crate::storage::StorageOpen;

g1_param::define!(self_endpoint_ipv4: Option<SocketAddr> = Some("0.0.0.0:6881".parse().unwrap()));
g1_param::define!(self_endpoint_ipv6: Option<SocketAddr> = None); // TODO: Enable IPv6.

g1_param::define!(tcp_listen_backlog: u32 = 256);

g1_param::define!(fetch_metadata_timeout: Duration = Duration::from_secs(60));

g1_param::define!(dht_lookup_peers_period: Duration = Duration::from_secs(600));

// Useful for testing.
g1_param::define!(peer_endpoints: Vec<SocketAddr> = Vec::new());
