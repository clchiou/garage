//! Base Library
//!
//! In general, the base library provides two kinds of features:
//! * Generic utility functions that are not in the Rust stdlib.
//! * Opinionated extension to the Rust stdlib.
//!
//! NOTE: The base library should only depend on the Rust stdlib.

// TODO: We enable `specialization` for now and will switch to `min_specialization` when it is
// sufficient for our use case in the `fmt` module.
#![allow(incomplete_features)]
#![allow(internal_features)]
#![feature(iterator_try_collect)]
#![feature(mutex_unlock)]
#![feature(rustc_attrs)]
#![feature(specialization)]
#![cfg_attr(feature = "collections_ext", feature(try_blocks))]
#![cfg_attr(test, feature(assert_matches))]
#![cfg_attr(test, feature(noop_waker))]

pub mod collections;
pub mod fmt;
pub mod future;
pub mod iter;
pub mod ops;
pub mod owner;
pub mod slice;
pub mod str;
pub mod sync;
pub mod task;

pub mod cmp {
    pub use g1_base_derive::PartialEqExt;
}
