//! Bipartite graph, also known as bigraph.
//!
//! `BiGraph<K, V>` tracks both `K -> V` and `V -> K`, enabling faster inverse lookups compared to
//! `Map<K, Set<V>>` but with higher memory overhead.  If faster lookups are not required, you may
//! use the latter instead.

mod hash;

pub use self::hash::NaiveHashBiGraph;
