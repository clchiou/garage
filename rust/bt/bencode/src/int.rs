use std::fmt;
use std::num::ParseIntError;
use std::str::FromStr;

pub(crate) trait Int: Copy + fmt::Display + FromStr<Err = ParseIntError> + Sized {}

impl Int for i8 {}
impl Int for i16 {}
impl Int for i32 {}
impl Int for i64 {}
impl Int for i128 {}
impl Int for isize {}
impl Int for u8 {}
impl Int for u16 {}
impl Int for u32 {}
impl Int for u64 {}
impl Int for u128 {}
impl Int for usize {}

// Larger than enough for `i128`.
pub(crate) const INTEGER_BUF_SIZE: usize = 64;
