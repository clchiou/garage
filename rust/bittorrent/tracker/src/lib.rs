#![feature(iterator_try_collect)]

pub mod client;
pub mod error;
pub mod request;
pub mod response;

mod tracker;

pub use crate::tracker::{Endpoint, PeerContactInfo, Torrent, Tracker, TrackerGuard};

g1_param::define!(peer_queue_size: usize = 128);
