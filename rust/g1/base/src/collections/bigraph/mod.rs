//! Bipartite graph, also known as bigraph.
//!
//! `BiGraph<K, V>` tracks both `K -> V` and `V -> K`, enabling faster inverse lookups compared to
//! `Map<K, Set<V>>` but with higher memory overhead.  If faster lookups are not required, you may
//! use the latter instead.

mod btree;
mod hash;
#[cfg(feature = "collections_ext")]
mod hash_ext;

// TODO: Factor out common code between `NaiveBTreeBiGraph` and `NaiveHashBiGraph`.
pub use self::btree::NaiveBTreeBiGraph;
pub use self::hash::NaiveHashBiGraph;
#[cfg(feature = "collections_ext")]
pub use self::hash_ext::{HashBiGraph, SetView};
