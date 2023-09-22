#![feature(io_error_other)]
#![cfg_attr(test, feature(io_error_downcast))]

pub mod error;

mod message;

pub use message::Message;
