#![feature(assert_matches)]
#![feature(debug_closure_helpers)]
#![feature(iterator_try_collect)]
#![feature(trait_alias)]

pub mod borrow;
pub mod error;
pub mod macros;
pub mod own;
pub mod value;

mod bstr;
mod de;
mod de_ext;
mod int;
mod json;
mod mut_ref;
mod raw;
mod ser;
mod yaml;

#[cfg(test)]
mod testing;

//
// Implementer's Notes:
//
// * Bencode is specified in BEP 3.
//
// * We represent the Serde data model in Bencode as faithfully as we can:
//
//   | Serde                        | Bencode                      |
//   |------------------------------|------------------------------|
//   | bool                         | 0 or 1                       |
//   | f32, f64                     | ok if fractional part == 0   |
//   | char                         | UTF-8 byte string            |
//   |------------------------------|------------------------------|
//   | Some(v)                      | [v]                          |
//   | None                         | []                           |
//   |------------------------------|------------------------------|
//   | ()                           | []                           |
//   | Unit                         | []                           |
//   | Enum::Unit                   | "Unit"                       |
//   |------------------------------|------------------------------|
//   | NewType(v)                   | v                            |
//   | Enum::NewType(v)             | {"NewType": v}               |
//   |------------------------------|------------------------------|
//   | Tuple(u, v)                  | [u, v]                       |
//   | Enum::Tuple(u, v)            | {"Tuple": [u, v]}            |
//   |------------------------------|------------------------------|
//   | Struct { x: v }              | {"x": v}                     |
//   | Enum::Struct { x: v }        | {"Struct": {"x": v}}         |
//
// * I am not sure if this is a good idea, but we divided the interface into pure-memory and I/O
//   functions, which resulted in one error type for each group of functions.
//

pub use crate::de::{
    from_buf, from_buf_strict, from_reader, from_reader_strict, from_slice, from_slice_strict,
};
pub use crate::ser::{to_buf, to_bytes, to_writer};
pub use crate::value::de::{from_borrowed_value, from_value};
pub use crate::value::ser::to_value;

// Prefer `own` to `borrow`.
pub use crate::own::{WithRaw, bytes::Value};

pub use crate::json::Json;
pub use crate::yaml::Yaml;
