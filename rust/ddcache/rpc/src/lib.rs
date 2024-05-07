pub mod rpc_capnp {
    include!(concat!(env!("OUT_DIR"), "/ddcache/rpc_capnp.rs"));
}

pub mod envelope;
pub mod service;

use std::net::SocketAddr;
use std::sync::Arc;

use bytes::Bytes;
use capnp::message;
use capnp::serialize;
use chrono::{DateTime, TimeZone, Utc};

use g1_capnp::{owner::Owner, result_capnp::result};
use g1_zmq::envelope::Frame;

use crate::rpc_capnp::{endpoint, error, request, response};

// TODO: Should we store this value in etcd instead?
g1_param::define!(pub num_replicas: usize = 2);

pub type Endpoint = Arc<str>;
pub type BlobEndpoint = SocketAddr;

pub type Timestamp = DateTime<Utc>;

pub type Token = u64;

pub type RequestOwner<Buffer = Frame> = Owner<Buffer, request::Reader<'static>>;
pub type ResponseOwner<Buffer = Frame> = Owner<Buffer, ResponseReader<'static>>;
pub type ResponseResultOwner<Buffer = Frame> = Owner<Buffer, ResponseResult<'static>>;

pub type ResponseReader<'a> = result::Reader<'a, response::Owned, error::Owned>;
pub type ResponseBuilder<'a> = result::Builder<'a, response::Owned, error::Owned>;

pub type ResponseResult<'a> = Result<Option<response::Reader<'a>>, error::Reader<'a>>;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Request {
    Cancel(Token),
    Read {
        key: Bytes,
    },
    ReadMetadata {
        key: Bytes,
    },
    Write {
        key: Bytes,
        metadata: Option<Bytes>,
        size: usize,
        expire_at: Option<Timestamp>,
    },
    WriteMetadata {
        key: Bytes,
        metadata: Option<Option<Bytes>>,
        expire_at: Option<Option<Timestamp>>,
    },
    Remove {
        key: Bytes,
    },
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Response {
    Cancel,
    Read {
        metadata: BlobMetadata,
        blob: BlobRequest,
    },
    ReadMetadata {
        metadata: BlobMetadata,
    },
    Write {
        blob: BlobRequest,
    },
    WriteMetadata {
        metadata: BlobMetadata,
    },
    Remove {
        metadata: BlobMetadata,
    },
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BlobMetadata {
    pub metadata: Option<Bytes>,
    pub size: usize,
    pub expire_at: Option<Timestamp>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BlobRequest {
    pub endpoint: BlobEndpoint,
    pub token: Token,
}

pub trait TimestampExt: Sized {
    fn now() -> Self;
    fn decode(timestamp: u64) -> Result<Option<Self>, u64>;
    fn encode(timestamp: Option<Self>) -> u64;
}

impl TimestampExt for Timestamp {
    fn now() -> Self {
        Utc::now()
    }

    fn decode(timestamp: u64) -> Result<Option<Self>, u64> {
        (timestamp != 0)
            .then(|| {
                i64::try_from(timestamp)
                    .ok()
                    .and_then(|t| Utc.timestamp_opt(t, 0).single())
                    .ok_or(timestamp)
            })
            .transpose()
    }

    fn encode(timestamp: Option<Self>) -> u64 {
        timestamp.map_or(0, |t| t.timestamp().try_into().unwrap())
    }
}

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
    pub fn set(&mut self, endpoint: &BlobEndpoint) {
        match endpoint {
            BlobEndpoint::V4(endpoint) => self.set_ipv4(u32::from_be_bytes(endpoint.ip().octets())),
            BlobEndpoint::V6(_) => unimplemented!(),
        }
        self.set_port(endpoint.port());
    }
}

impl<'a> TryFrom<request::Reader<'a>> for Request {
    type Error = capnp::Error;

    fn try_from(request: request::Reader<'a>) -> Result<Self, Self::Error> {
        Ok(match request.which()? {
            request::Cancel(token) => Self::Cancel(token),

            request::Read(request) => Self::Read {
                key: to_key(request?.get_key()?)?,
            },

            request::ReadMetadata(request) => Self::ReadMetadata {
                key: to_key(request?.get_key()?)?,
            },

            request::Write(request) => {
                let request = request?;
                Self::Write {
                    key: to_key(request.get_key()?)?,
                    metadata: to_metadata(request.get_metadata()?),
                    size: to_size(request.get_size()),
                    expire_at: to_expire_at(request.get_expire_at())?,
                }
            }

            request::WriteMetadata(request) => {
                let request = request?;
                Self::WriteMetadata {
                    key: to_key(request.get_key()?)?,
                    metadata: match request.get_metadata().which()? {
                        request::write_metadata::metadata::Dont(()) => None,
                        request::write_metadata::metadata::Write(metadata) => {
                            Some(to_metadata(metadata?))
                        }
                    },
                    expire_at: match request.get_expire_at().which()? {
                        request::write_metadata::expire_at::Dont(()) => None,
                        request::write_metadata::expire_at::Write(expire_at) => {
                            Some(to_expire_at(expire_at)?)
                        }
                    },
                }
            }

            request::Remove(request) => Self::Remove {
                key: to_key(request?.get_key()?)?,
            },
        })
    }
}

impl From<Request> for Vec<u8> {
    fn from(request: Request) -> Self {
        let mut message = message::Builder::new_default();
        message.init_root::<request::Builder>().set(&request);
        serialize::write_message_to_words(&message)
    }
}

impl<'a> request::Builder<'a> {
    pub fn set(&mut self, request: &Request) {
        let mut this = self.reborrow();
        match request {
            Request::Cancel(token) => this.set_cancel(*token),

            Request::Read { key } => {
                assert!(!key.is_empty());
                this.init_read().set_key(key);
            }

            Request::ReadMetadata { key } => {
                assert!(!key.is_empty());
                this.init_read_metadata().set_key(key);
            }

            Request::Write {
                key,
                metadata,
                size,
                expire_at,
            } => {
                assert!(!key.is_empty());
                let mut this = this.init_write();
                this.set_key(key);
                this.set_metadata(metadata.as_deref().unwrap_or(&[]));
                this.set_size((*size).try_into().unwrap());
                this.set_expire_at(Timestamp::encode(*expire_at));
            }

            Request::WriteMetadata {
                key,
                metadata,
                expire_at,
            } => {
                assert!(!key.is_empty());
                let mut this = this.init_write_metadata();
                this.set_key(key);
                if let Some(metadata) = metadata {
                    this.reborrow()
                        .init_metadata()
                        .set_write(metadata.as_deref().unwrap_or(&[]));
                }
                if let Some(expire_at) = expire_at {
                    this.reborrow()
                        .init_expire_at()
                        .set_write(Timestamp::encode(*expire_at));
                }
            }

            Request::Remove { key } => {
                assert!(!key.is_empty());
                this.init_remove().set_key(key);
            }
        }
    }
}

impl<'a> TryFrom<response::Reader<'a>> for Response {
    type Error = capnp::Error;

    fn try_from(response: response::Reader<'a>) -> Result<Self, Self::Error> {
        Ok(match response.which()? {
            response::Cancel(()) => Self::Cancel,

            response::Read(response) => {
                let response = response?;
                Self::Read {
                    metadata: response.get_metadata()?.try_into()?,
                    blob: response.get_blob()?.try_into()?,
                }
            }

            response::ReadMetadata(response) => Self::ReadMetadata {
                metadata: response?.get_metadata()?.try_into()?,
            },

            response::Write(response) => Self::Write {
                blob: response?.get_blob()?.try_into()?,
            },

            response::WriteMetadata(response) => Self::WriteMetadata {
                metadata: response?.get_metadata()?.try_into()?,
            },

            response::Remove(response) => Self::Remove {
                metadata: response?.get_metadata()?.try_into()?,
            },
        })
    }
}

// Encodes as `Ok(Some(response))`.
impl From<Response> for Vec<u8> {
    fn from(response: Response) -> Self {
        let mut message = message::Builder::new_default();
        message
            .init_root::<ResponseBuilder>()
            .init_ok()
            .set(&response);
        serialize::write_message_to_words(&message)
    }
}

impl<'a> response::Builder<'a> {
    pub fn set(&mut self, response: &Response) {
        let mut this = self.reborrow();
        match response {
            Response::Cancel => this.set_cancel(()),

            Response::Read { metadata, blob } => {
                let mut this = this.init_read();
                this.reborrow().init_metadata().set(metadata);
                this.reborrow().init_blob().set(blob);
            }

            Response::ReadMetadata { metadata } => {
                this.init_read_metadata().init_metadata().set(metadata)
            }

            Response::Write { blob } => this.init_write().init_blob().set(blob),

            Response::WriteMetadata { metadata } => {
                this.init_write_metadata().init_metadata().set(metadata)
            }

            Response::Remove { metadata } => this.init_remove().init_metadata().set(metadata),
        }
    }
}

impl<'a> TryFrom<response::metadata::Reader<'a>> for BlobMetadata {
    type Error = capnp::Error;

    fn try_from(metadata: response::metadata::Reader<'a>) -> Result<Self, Self::Error> {
        Ok(Self {
            metadata: to_metadata(metadata.get_metadata()?),
            size: to_size(metadata.get_size()),
            expire_at: to_expire_at(metadata.get_expire_at())?,
        })
    }
}

impl<'a> response::metadata::Builder<'a> {
    pub fn set(&mut self, metadata: &BlobMetadata) {
        self.set_metadata(metadata.metadata.as_deref().unwrap_or(&[]));
        self.set_size(metadata.size.try_into().unwrap());
        self.set_expire_at(Timestamp::encode(metadata.expire_at));
    }
}

impl<'a> TryFrom<response::blob_request::Reader<'a>> for BlobRequest {
    type Error = capnp::Error;

    fn try_from(blob: response::blob_request::Reader<'a>) -> Result<Self, Self::Error> {
        Ok(Self {
            endpoint: blob.get_endpoint()?.try_into()?,
            token: blob.get_token(),
        })
    }
}

impl<'a> response::blob_request::Builder<'a> {
    pub fn set(&mut self, blob: &BlobRequest) {
        self.reborrow().init_endpoint().set(&blob.endpoint);
        self.set_token(blob.token);
    }
}

fn to_key(key: &[u8]) -> Result<Bytes, capnp::Error> {
    if key.is_empty() {
        Err(capnp::Error {
            kind: capnp::ErrorKind::Failed,
            extra: "empty key".to_string(),
        })
    } else {
        Ok(Bytes::copy_from_slice(key))
    }
}

fn to_metadata(metadata: &[u8]) -> Option<Bytes> {
    (!metadata.is_empty()).then(|| Bytes::copy_from_slice(metadata))
}

fn to_size(size: u32) -> usize {
    size.try_into().unwrap()
}

fn to_expire_at(expire_at: u64) -> Result<Option<Timestamp>, capnp::Error> {
    Timestamp::decode(expire_at).map_err(|expire_at| capnp::Error {
        kind: capnp::ErrorKind::Failed,
        extra: format!("invalid expire_at: {expire_at}"),
    })
}
