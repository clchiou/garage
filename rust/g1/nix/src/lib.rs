#![feature(try_blocks)] // TODO: Why can I not condition this with `cfg_attr(test, ...)`?

pub mod fcntl;
pub mod sys;
