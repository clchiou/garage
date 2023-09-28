#![feature(result_option_inspect)]
#![cfg_attr(test, feature(assert_matches))]
#![cfg_attr(test, feature(is_sorted))]

mod chan;
mod incoming;
mod outgoing;
mod state;

use bytes::Bytes;

use bittorrent_base::PieceIndex;

g1_param::define!(interested_queue_size: usize = 256);
g1_param::define!(request_queue_size: usize = 256);

g1_param::define!(possession_queue_size: usize = 256);
g1_param::define!(suggest_queue_size: usize = 256);
g1_param::define!(allowed_fast_queue_size: usize = 256);
g1_param::define!(block_queue_size: usize = 256);

g1_param::define!(port_queue_size: usize = 256);

g1_param::define!(extension_queue_size: usize = 256);

pub use chan::{new_channels, Endpoint, Recvs, Sends};

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
