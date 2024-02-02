mod net;
mod storage;

use std::net::SocketAddr;

pub use crate::storage::StorageOpen;

g1_param::define!(self_endpoint_ipv4: Option<SocketAddr> = Some("0.0.0.0:6881".parse().unwrap()));
g1_param::define!(self_endpoint_ipv6: Option<SocketAddr> = None); // TODO: Enable IPv6.

g1_param::define!(tcp_listen_backlog: u32 = 256);
