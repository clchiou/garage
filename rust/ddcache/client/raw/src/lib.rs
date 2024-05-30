#![feature(try_blocks)]

pub mod concurrent;

mod actor;
mod blob;
mod error;
mod response;

use std::io;
use std::sync::Arc;
use std::time::Duration;

use bytes::Bytes;
use capnp::serialize;
use snafu::prelude::*;
use tokio::sync::{mpsc, oneshot, watch};
use tracing::Instrument;
use uuid::Uuid;
use zmq::{Context, REQ};

use g1_tokio::sync::watch::Update;
use g1_tokio::task::{Cancel, JoinGuard};
use g1_zmq::Socket;

use ddcache_rpc::service::Server;
use ddcache_rpc::{Endpoint, ResponseReader, Timestamp, Token};

use crate::actor::{Actor, RequestSend, ServerSend};
use crate::error::{DecodeSnafu, RequestSnafu, UnexpectedResponseSnafu};
use crate::response::ResponseResult;

g1_param::define!(
    request_timeout: Duration = Duration::from_secs(2);
    parse = g1_param::parse::duration;
);
g1_param::define!(
    blob_request_timeout: Duration = Duration::from_secs(8);
    parse = g1_param::parse::duration;
);

pub use crate::blob::RemoteBlob;
pub use crate::error::Error;
pub use crate::response::Response;

#[derive(Clone, Debug)]
pub struct RawClient {
    // TODO: Remove `Arc` after we upgrade `tokio` to v1.37.0.
    server_send: Arc<ServerSend>,
    request_send: RequestSend,
    cancel: Cancel,
}

pub type RawClientGuard = JoinGuard<Result<(), io::Error>>;

#[derive(Debug)]
pub struct RawNaiveClient(Socket);

macro_rules! define_methods {
    ($($mut:ident)? $(,)?) => {
        pub async fn cancel(&$($mut)* self, token: Token) -> Result<(), Error> {
            let response = self.request(ddcache_rpc::Request::Cancel(token)).await?;
            ensure!(response.is_none(), UnexpectedResponseSnafu);
            Ok(())
        }

        pub async fn read(&$($mut)* self, key: Bytes) -> ResponseResult {
            self.request(ddcache_rpc::Request::Read { key }).await
        }

        pub async fn read_metadata(&$($mut)* self, key: Bytes) -> ResponseResult {
            self.request(ddcache_rpc::Request::ReadMetadata { key })
                .await
        }

        pub async fn write(
            &$($mut)* self,
            key: Bytes,
            metadata: Option<Bytes>,
            size: usize,
            expire_at: Option<Timestamp>,
        ) -> ResponseResult {
            self.request(ddcache_rpc::Request::Write {
                key,
                metadata,
                size,
                expire_at,
            })
            .await
        }

        pub async fn write_metadata(
            &$($mut)* self,
            key: Bytes,
            metadata: Option<Option<Bytes>>,
            expire_at: Option<Option<Timestamp>>,
        ) -> ResponseResult {
            self.request(ddcache_rpc::Request::WriteMetadata {
                key,
                metadata,
                expire_at,
            })
            .await
        }

        pub async fn remove(&$($mut)* self, key: Bytes) -> ResponseResult {
            self.request(ddcache_rpc::Request::Remove { key }).await
        }

        pub async fn pull(&$($mut)* self, key: Bytes) -> ResponseResult {
            self.request(ddcache_rpc::Request::Pull { key }).await
        }

        pub async fn push(
            &$($mut)* self,
            key: Bytes,
            metadata: Option<Bytes>,
            size: usize,
            expire_at: Option<Timestamp>,
        ) -> ResponseResult {
            self.request(ddcache_rpc::Request::Push {
                key,
                metadata,
                size,
                expire_at,
            })
            .await
        }
    };
}

impl RawClient {
    pub fn connect(id: Uuid, server: Server) -> (Self, RawClientGuard) {
        let (server_send, server_recv) = watch::channel(server);
        let (request_send, request_recv) = mpsc::channel(16);
        let guard = RawClientGuard::spawn(move |cancel| {
            Actor::new(cancel, server_recv, request_recv)
                .run()
                .instrument(tracing::info_span!("ddcache/raw", %id))
        });
        (
            Self {
                server_send: Arc::new(server_send),
                request_send,
                cancel: guard.cancel_handle(),
            },
            guard,
        )
    }

    pub fn update(&self, server: Server) {
        self.server_send.update(server);
    }

    pub fn disconnect(&self) {
        self.cancel.set();
    }

    async fn request(&self, request: ddcache_rpc::Request) -> ResponseResult {
        let (response_send, response_recv) = oneshot::channel();
        self.request_send
            .send((request, response_send))
            .await
            .map_err(|_| Error::Stopped)?;
        response_recv.await.map_err(|_| Error::Stopped)?
    }

    define_methods!();
}

impl From<Socket> for RawNaiveClient {
    fn from(socket: Socket) -> Self {
        Self::with_socket(socket)
    }
}

impl From<RawNaiveClient> for Socket {
    fn from(client: RawNaiveClient) -> Self {
        client.into_socket()
    }
}

impl RawNaiveClient {
    pub fn connect(endpoint: Endpoint) -> Result<Self, io::Error> {
        tracing::info!(%endpoint, "connect");
        let mut socket = Socket::try_from(Context::new().socket(REQ)?)?;
        socket.set_linger(0)?; // Do NOT block the program exit!
        socket.connect(&endpoint)?;
        Ok(Self::with_socket(socket))
    }

    pub fn with_socket(socket: Socket) -> Self {
        Self(socket)
    }

    pub fn into_socket(self) -> Socket {
        self.0
    }

    async fn request(&mut self, request: ddcache_rpc::Request) -> ResponseResult {
        tracing::debug!(?request);
        let response: Result<_, io::Error> = try {
            self.0.send(Vec::<u8>::from(request), 0).await?;
            self.0.recv_msg(0).await?
        };
        let response = response.context(RequestSnafu)?;

        let response: Result<_, capnp::Error> = try {
            let response =
                serialize::read_message_from_flat_slice(&mut &*response, Default::default())?;
            match ddcache_rpc::ResponseResult::try_from(response.get_root::<ResponseReader>()?)? {
                Ok(Some(response)) => Ok(Response::try_from(response)?),
                Ok(None) => Ok(None),
                Err(error) => Err(Error::try_from(error)?),
            }
        };
        let response = response.context(DecodeSnafu)?;
        tracing::debug!(?response);
        response
    }

    define_methods!(mut);
}
