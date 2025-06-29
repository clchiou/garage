pub mod bytes;
pub mod bytes_mut;
pub mod vec;

extern crate bytes as bytes_crate;

use crate::raw;

pub type WithRaw<T> = raw::WithRaw<T, bytes_crate::Bytes>;
