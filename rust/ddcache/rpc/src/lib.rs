pub mod rpc_capnp {
    include!(concat!(env!("OUT_DIR"), "/ddcache/rpc_capnp.rs"));
}

pub mod envelope;
pub mod service;

use std::net::SocketAddr;
use std::sync::Arc;

use g1_capnp::{owner::Owner, result_capnp::result};
use g1_zmq::envelope::Frame;

use crate::rpc_capnp::{endpoint, error, request, response};

pub type Endpoint = Arc<str>;
pub type BlobEndpoint = SocketAddr;

pub type Token = u64;

pub type RequestOwner<Buffer = Frame> = Owner<Buffer, request::Reader<'static>>;
pub type ResponseOwner<Buffer = Frame> = Owner<Buffer, ResponseReader<'static>>;
pub type ResponseResultOwner<Buffer = Frame> = Owner<Buffer, ResponseResult<'static>>;

pub type ResponseReader<'a> = result::Reader<'a, response::Owned, error::Owned>;
pub type ResponseBuilder<'a> = result::Builder<'a, response::Owned, error::Owned>;

pub type ResponseResult<'a> = Result<Option<response::Reader<'a>>, error::Reader<'a>>;

impl<'a> TryFrom<endpoint::Reader<'a>> for BlobEndpoint {
    type Error = capnp::Error;

    fn try_from(endpoint: endpoint::Reader<'a>) -> Result<Self, Self::Error> {
        // At the moment, this function is actually infallible.
        Ok(Self::new(
            endpoint.get_ipv4().to_be_bytes().into(),
            endpoint.get_port(),
        ))
    }
}

impl<'a> endpoint::Builder<'a> {
    pub fn set(&mut self, endpoint: BlobEndpoint) {
        match endpoint {
            BlobEndpoint::V4(endpoint) => self.set_ipv4(u32::from_be_bytes(endpoint.ip().octets())),
            BlobEndpoint::V6(_) => unimplemented!(),
        }
        self.set_port(endpoint.port());
    }
}
