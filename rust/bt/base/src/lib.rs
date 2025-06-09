#![feature(debug_closure_helpers)]
#![feature(generic_arg_infer)]
#![feature(ip_as_octets)]
#![feature(ip_from)]
#![feature(iterator_try_collect)]
#![feature(trait_alias)]
#![feature(try_blocks)]

pub mod compact;
pub mod info_hash;
pub mod magnet_uri;
pub mod node_id;
pub mod peer_id;

pub use crate::compact::Compact;
pub use crate::info_hash::InfoHash;
pub use crate::magnet_uri::MagnetUri;
pub use crate::node_id::{NodeDistance, NodeId};
pub use crate::peer_id::PeerId;
