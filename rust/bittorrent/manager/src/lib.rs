pub mod error;

mod actor;
mod manager;
mod net;

use std::net::SocketAddr;
use std::time::Duration;

use g1_tokio::io::DynStream;

g1_param::define!(update_queue_size: usize = 256);

g1_param::define!(
    connect_timeout: Duration = Duration::from_secs(4);
    parse = g1_param::parse::duration;
);

pub use crate::manager::{Manager, ManagerGuard};

pub type Preference = (Transport, Cipher);

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Transport {
    Tcp,
    Utp,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Cipher {
    Mse,
    Plaintext,
}

// NOTE: For now, we use the peer endpoint to uniquely identify a peer, regardless of the transport
// layer protocol (TCP vs uTP) used by the peer.
pub type Endpoint = SocketAddr;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Update {
    Start,
    Stop,
}

pub(crate) type Socket = bittorrent_socket::Socket<DynStream<'static>>;
