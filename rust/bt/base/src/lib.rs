#![feature(debug_closure_helpers)]
#![feature(generic_arg_infer)]
#![feature(ip_as_octets)]
#![feature(ip_from)]
#![feature(iterator_try_collect)]
#![feature(trait_alias)]
#![feature(try_blocks)]

pub mod compact;
pub mod info_hash;
pub mod layout;
pub mod magnet_uri;
pub mod node_id;
pub mod peer_id;
pub mod piece_hash;

pub use crate::compact::Compact;
pub use crate::info_hash::InfoHash;
pub use crate::layout::{BlockRange, Layout, PieceIndex};
pub use crate::magnet_uri::MagnetUri;
pub use crate::node_id::{NodeDistance, NodeId};
pub use crate::peer_id::PeerId;
pub use crate::piece_hash::{PieceHash, PieceHashes};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Features {
    pub dht: bool,       // BEP 5
    pub fast: bool,      // BEP 6
    pub extension: bool, // BEP 10
}
