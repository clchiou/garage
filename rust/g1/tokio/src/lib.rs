//! Extends the `tokio` crate.

#![cfg_attr(feature = "icmp", feature(raw_os_error_ty))]
#![cfg_attr(test, feature(assert_matches))]
#![cfg_attr(test, feature(binary_heap_into_iter_sorted))]

pub mod bstream;
pub mod io;
pub mod net;
pub mod os;
pub mod sync;
pub mod task;
pub mod time;
