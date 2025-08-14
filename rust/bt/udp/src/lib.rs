#![feature(trait_alias)]

use std::io::Error;
use std::net::SocketAddr;

use bytes::Bytes;
use futures::sink;
use futures::stream;

pub trait Stream =
    stream::Stream<Item = Result<(SocketAddr, Bytes), Error>> + Send + Unpin + 'static;
pub trait Sink = sink::Sink<(SocketAddr, Bytes), Error = Error> + Send + Unpin + 'static;
