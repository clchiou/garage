pub mod rpc_capnp {
    // TODO: Remove `clippy::needless_lifetimes` after [#522] has been fixed.
    // [#522]: https://github.com/capnproto/capnproto-rust/issues/522
    #![allow(clippy::needless_lifetimes, clippy::uninlined_format_args)]
    include!(concat!(env!("OUT_DIR"), "/dkvcache/rpc_capnp.rs"));
}

pub mod envelope;
pub mod service;

use std::sync::Arc;

use bytes::Bytes;
use capnp::message;
use capnp::serialize;
use snafu::prelude::*;

use g1_capnp::result_capnp::result;

use crate::rpc_capnp::{error, request, response};

// TODO: Should we store this value in etcd instead?
g1_param::define!(pub num_replicas: usize = 2);

pub type Endpoint = Arc<str>;

pub use g1_chrono::{Timestamp, TimestampExt};

pub type ResponseResult = Result<Option<Response>, Error>;

type ResponseReader<'a> = result::Reader<'a, response::Owned, error::Owned>;
type ResponseBuilder<'a> = result::Builder<'a, response::Owned, error::Owned>;

type ResponseResultReader<'a> = Result<Option<response::Reader<'a>>, error::Reader<'a>>;

// For now, empty keys and values are not allowed.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Request {
    Ping,

    //
    // Client-Server Protocol
    //
    Get {
        key: Bytes,
    },
    Set {
        key: Bytes,
        value: Bytes,
        expire_at: Option<Timestamp>,
    },
    Update {
        key: Bytes,
        value: Option<Bytes>,
        expire_at: Option<Option<Timestamp>>,
    },
    Remove {
        key: Bytes,
    },

    //
    // Peer Protocol
    //
    Pull {
        key: Bytes,
    },
    Push {
        key: Bytes,
        value: Bytes,
        expire_at: Option<Timestamp>,
    },
}

// For now, empty values are not allowed.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Response {
    pub value: Bytes,
    pub expire_at: Option<Timestamp>,
}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Error {
    #[snafu(display("server error"))]
    Server,

    #[snafu(display("server unavailable"))]
    Unavailable,

    #[snafu(display("invalid request error"))]
    InvalidRequest,
    // More refined invalid request errors.
    #[snafu(display("max key size exceeded: {max}"))]
    MaxKeySizeExceeded { max: u32 },
    #[snafu(display("max value size exceeded: {max}"))]
    MaxValueSizeExceeded { max: u32 },
}

impl<'a> TryFrom<&'a [u8]> for Request {
    type Error = capnp::Error;

    fn try_from(mut request: &'a [u8]) -> Result<Self, Self::Error> {
        let message = serialize::read_message_from_flat_slice(&mut request, Default::default())?;
        message.get_root::<request::Reader>()?.try_into()
    }
}

impl<'a> TryFrom<request::Reader<'a>> for Request {
    type Error = capnp::Error;

    fn try_from(request: request::Reader<'a>) -> Result<Self, Self::Error> {
        Ok(match request.which()? {
            request::Ping(()) => Self::Ping,

            request::Get(request) => Self::Get {
                key: to_key(request?.get_key()?)?,
            },

            request::Set(request) => {
                let request = request?;
                Self::Set {
                    key: to_key(request.get_key()?)?,
                    value: to_value(request.get_value()?)?,
                    expire_at: to_expire_at(request.get_expire_at())?,
                }
            }

            request::Update(request) => {
                let request = request?;
                Self::Update {
                    key: to_key(request.get_key()?)?,
                    value: match request.get_value().which()? {
                        request::update::value::Dont(()) => None,
                        request::update::value::Set(value) => Some(to_value(value?)?),
                    },
                    expire_at: match request.get_expire_at().which()? {
                        request::update::expire_at::Dont(()) => None,
                        request::update::expire_at::Set(expire_at) => {
                            Some(to_expire_at(expire_at)?)
                        }
                    },
                }
            }

            request::Remove(request) => Self::Remove {
                key: to_key(request?.get_key()?)?,
            },

            request::Pull(request) => Self::Pull {
                key: to_key(request?.get_key()?)?,
            },

            request::Push(request) => {
                let request = request?;
                Self::Push {
                    key: to_key(request.get_key()?)?,
                    value: to_value(request.get_value()?)?,
                    expire_at: to_expire_at(request.get_expire_at())?,
                }
            }
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

impl request::Builder<'_> {
    pub fn set(&mut self, request: &Request) {
        let mut this = self.reborrow();
        match request {
            Request::Ping => this.set_ping(()),

            Request::Get { key } => {
                assert!(!key.is_empty());
                this.init_get().set_key(key);
            }

            Request::Set {
                key,
                value,
                expire_at,
            } => {
                assert!(!key.is_empty());
                assert!(!value.is_empty());
                let mut this = this.init_set();
                this.set_key(key);
                this.set_value(value);
                this.set_expire_at(expire_at.timestamp_u64());
            }

            Request::Update {
                key,
                value,
                expire_at,
            } => {
                assert!(!key.is_empty());
                let mut this = this.init_update();
                this.set_key(key);
                if let Some(value) = value {
                    assert!(!value.is_empty());
                    this.reborrow().init_value().set_set(value);
                }
                if let Some(expire_at) = expire_at {
                    this.reborrow()
                        .init_expire_at()
                        .set_set(expire_at.timestamp_u64());
                }
            }

            Request::Remove { key } => {
                assert!(!key.is_empty());
                this.init_remove().set_key(key);
            }

            Request::Pull { key } => {
                assert!(!key.is_empty());
                this.init_pull().set_key(key);
            }

            Request::Push {
                key,
                value,
                expire_at,
            } => {
                assert!(!key.is_empty());
                assert!(!value.is_empty());
                let mut this = this.init_push();
                this.set_key(key);
                this.set_value(value);
                this.set_expire_at(expire_at.timestamp_u64());
            }
        }
    }
}

pub trait ResponseResultExt: Sized {
    fn decode(result: &[u8]) -> Result<Self, capnp::Error>;
    fn encode(result: Self) -> Vec<u8>;
}

impl ResponseResultExt for ResponseResult {
    fn decode(mut result: &[u8]) -> Result<Self, capnp::Error> {
        let message = serialize::read_message_from_flat_slice(&mut result, Default::default())?;
        let reader = message.get_root::<ResponseReader>()?;
        Ok(match ResponseResultReader::try_from(reader)? {
            Ok(response) => Ok(response.map(|response| response.try_into()).transpose()?),
            Err(error) => Err(error.try_into()?),
        })
    }

    fn encode(result: Self) -> Vec<u8> {
        let mut message = message::Builder::new_default();
        let builder = message.init_root::<ResponseBuilder>();
        match result {
            Ok(Some(response)) => builder.init_ok().set(&response),
            Ok(None) => {}
            Err(error) => builder.init_err().set(&error),
        }
        serialize::write_message_to_words(&message)
    }
}

impl<'a> TryFrom<response::Reader<'a>> for Response {
    type Error = capnp::Error;

    fn try_from(response: response::Reader<'a>) -> Result<Self, Self::Error> {
        Ok(Self {
            value: to_value(response.get_value()?)?,
            expire_at: to_expire_at(response.get_expire_at())?,
        })
    }
}

impl response::Builder<'_> {
    pub fn set(&mut self, response: &Response) {
        self.set_value(&response.value);
        self.set_expire_at(response.expire_at.timestamp_u64());
    }
}

impl<'a> TryFrom<error::Reader<'a>> for Error {
    type Error = capnp::Error;

    fn try_from(error: error::Reader<'a>) -> Result<Self, Self::Error> {
        Ok(match error.which()? {
            error::Server(()) => Self::Server,
            error::Unavailable(()) => Self::Unavailable,
            error::InvalidRequest(()) => Self::InvalidRequest,
            error::MaxKeySizeExceeded(max) => Self::MaxKeySizeExceeded { max },
            error::MaxValueSizeExceeded(max) => Self::MaxValueSizeExceeded { max },
        })
    }
}

impl error::Builder<'_> {
    pub fn set(&mut self, error: &Error) {
        match error {
            Error::Server => self.set_server(()),
            Error::Unavailable => self.set_unavailable(()),
            Error::InvalidRequest => self.set_invalid_request(()),
            Error::MaxKeySizeExceeded { max } => self.set_max_key_size_exceeded(*max),
            Error::MaxValueSizeExceeded { max } => self.set_max_value_size_exceeded(*max),
        }
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

fn to_value(value: &[u8]) -> Result<Bytes, capnp::Error> {
    if value.is_empty() {
        Err(capnp::Error {
            kind: capnp::ErrorKind::Failed,
            extra: "empty value".to_string(),
        })
    } else {
        Ok(Bytes::copy_from_slice(value))
    }
}

fn to_expire_at(expire_at: u64) -> Result<Option<Timestamp>, capnp::Error> {
    <Option<Timestamp>>::from_timestamp_secs(expire_at).map_err(|expire_at| capnp::Error {
        kind: capnp::ErrorKind::Failed,
        extra: format!("invalid expire_at: {expire_at}"),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn none_response() -> Result<(), capnp::Error> {
        assert_eq!(
            ResponseResult::decode(&ResponseResult::encode(Ok(None)))?,
            Ok(None),
        );
        Ok(())
    }
}
