#![feature(try_blocks)]
#![cfg_attr(test, feature(assert_matches))]

pub mod handshake;
pub mod message;
pub mod tcp;

use std::io;

use futures::sink::Sink;
use futures::stream::Stream;

pub use crate::handshake::Handshaker;
pub use crate::message::Message;

// Fix the lifetime to `'static` for now, since I cannot think of any non-`'static` use cases.
// TODO: Should we use `Pin<Box<...>>` (`futures::stream::BoxStream`) instead?
pub type BoxStream =
    Box<dyn Stream<Item = Result<Message, message::Error>> + Send + Unpin + 'static>;
pub type BoxSink = Box<dyn Sink<Message, Error = io::Error> + Send + Unpin + 'static>;
