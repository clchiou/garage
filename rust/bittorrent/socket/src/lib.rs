#![feature(io_error_other)]
#![cfg_attr(test, feature(box_into_inner))]
#![cfg_attr(test, feature(io_error_downcast))]

pub mod error;

mod handshake;
mod message;

use std::time::Duration;

pub use message::Message;

g1_param::define!(handshake_timeout: Duration = Duration::from_secs(8));
