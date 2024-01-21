#[cfg(feature = "collections_ext")]
pub mod index_map;
pub mod vec_list;

mod table;

#[cfg(feature = "collections_ext")]
pub use self::index_map::HashIndexMap;
pub use self::table::HashBasedTable;
pub use self::vec_list::VecList;

// Default to stdlib's default hash builder, not hashbrown's.
#[cfg(feature = "collections_ext")]
type DefaultHashBuilder = std::collections::hash_map::RandomState;
