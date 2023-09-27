#![feature(result_option_inspect)]
#![cfg_attr(test, feature(assert_matches))]

mod incoming;
mod state;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Full;

pub use crate::incoming::ResponseSend;
