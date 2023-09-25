//! Extends the `tokio` crate.

#![feature(io_error_other)]
#![cfg_attr(feature = "icmp", feature(raw_os_error_ty))]
#![cfg_attr(feature = "icmp", feature(result_option_inspect))]
#![cfg_attr(test, feature(assert_matches))]

pub mod bstream;
pub mod io;
pub mod net;
pub mod sync;
pub mod task;
