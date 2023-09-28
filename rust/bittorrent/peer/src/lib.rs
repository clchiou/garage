#![feature(result_option_inspect)]
#![cfg_attr(test, feature(assert_matches))]
#![cfg_attr(test, feature(is_sorted))]

mod incoming;
mod outgoing;
mod state;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Full;

pub use crate::incoming::ResponseSend;
pub use crate::outgoing::ResponseRecv;
