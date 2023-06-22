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
#![feature(assert_matches)]
#![feature(iterator_try_collect)]
#![feature(return_position_impl_trait_in_trait)]
#![feature(rustc_attrs)]
#![feature(specialization)]

pub mod fmt;
pub mod ops;
pub mod owner;
pub mod slice;
pub mod str;

pub mod cmp {
    pub use g1_base_derive::PartialEqExt;
}
