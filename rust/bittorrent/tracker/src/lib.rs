#![feature(iterator_try_collect)]

pub mod agent;
pub mod client;
pub mod error;
pub mod request;
pub mod response;

use std::time::Duration;

pub use agent::{Agent, Endpoint, PeerContactInfo, Torrent};

g1_param::define!(peer_queue_size: usize = 128);
g1_param::define!(grace_period: Duration = Duration::from_secs(2));
