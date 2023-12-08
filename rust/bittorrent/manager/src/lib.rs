pub mod error;

mod actor;
mod agent;
mod net;

use std::net::SocketAddr;
use std::time::Duration;

use g1_tokio::io::DynStream;

g1_param::define!(update_queue_size: usize = 256);
g1_param::define!(grace_period: Duration = Duration::from_secs(2));

g1_param::define!(connect_timeout: Duration = Duration::from_secs(4));

pub use self::agent::Manager;

pub type Preference = (Transport, Cipher);

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Transport {
    Tcp,
    Utp,
}

pub(crate) const TRANSPORTS: &[Transport] = &[Transport::Tcp, Transport::Utp];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Cipher {
    Mse,
    Plaintext,
}

pub(crate) const CIPHERS: &[Cipher] = &[Cipher::Mse, Cipher::Plaintext];

// NOTE: For now, we use the peer endpoint to uniquely identify a peer, regardless of the transport
// layer protocol (TCP vs uTP) used by the peer.
pub type Endpoint = SocketAddr;

pub(crate) type Socket = bittorrent_socket::Socket<DynStream<'static>>;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Update {
    Start,
    Stop,
}
