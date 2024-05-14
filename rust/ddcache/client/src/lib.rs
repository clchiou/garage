#![feature(try_blocks)]

mod client;
mod error;

pub use ddcache_rpc::{BlobMetadata, Timestamp};

pub use crate::client::{Client, ClientGuard};
pub use crate::error::Error;
