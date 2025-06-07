#![feature(debug_closure_helpers)]
#![feature(ip_as_octets)]
#![feature(ip_from)]
#![feature(trait_alias)]
#![feature(try_blocks)]

pub mod compact;
pub mod info_hash;
pub mod node_id;
pub mod peer_id;

pub use crate::compact::Compact;
pub use crate::info_hash::InfoHash;
pub use crate::node_id::{NodeDistance, NodeId};
pub use crate::peer_id::PeerId;
