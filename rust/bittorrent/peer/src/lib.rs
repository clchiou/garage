#![cfg_attr(test, feature(assert_matches))]
#![cfg_attr(test, feature(is_sorted))]

pub mod error;

mod actor;
mod agent;
mod chan;
mod incoming;
mod outgoing;
mod state;

use std::time::Duration;

use bytes::Bytes;

use bittorrent_base::PieceIndex;

g1_param::define!(request_timeout: Duration = Duration::from_secs(16));
g1_param::define!(grace_period: Duration = Duration::from_secs(2));

g1_param::define!(recv_keep_alive_timeout: Duration = Duration::from_secs(120));
// This is slightly shorter than `recv_keep_alive_timeout` because we aim to send a `KeepAlive`
// message before the peer times out.
g1_param::define!(send_keep_alive_timeout: Duration = Duration::from_secs(100));

g1_param::define!(interested_queue_size: usize = 256);
g1_param::define!(request_queue_size: usize = 256);

g1_param::define!(possession_queue_size: usize = 256);
g1_param::define!(suggest_queue_size: usize = 256);
g1_param::define!(allowed_fast_queue_size: usize = 256);
g1_param::define!(block_queue_size: usize = 256);

g1_param::define!(port_queue_size: usize = 256);

g1_param::define!(extension_queue_size: usize = 256);

pub use agent::Agent;
pub use chan::{new_channels, Endpoint, ExtensionMessageOwner, Recvs, Sends};

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Incompatible;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Full;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Possession {
    Bitfield(Bytes),
    Have(PieceIndex),
    HaveAll,
    HaveNone,
}

pub use crate::incoming::ResponseSend;
pub use crate::outgoing::ResponseRecv;
