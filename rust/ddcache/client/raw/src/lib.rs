#![feature(try_blocks)]

mod actor;
mod blob;
mod error;
mod response;

use std::io;
use std::time::Duration;

use bytes::Bytes;
use snafu::prelude::*;
use tokio::sync::{mpsc, oneshot};
use tracing::Instrument;
use zmq::{Context, DEALER};

use g1_tokio::task::{Cancel, JoinGuard};
use g1_zmq::Socket;

use ddcache_rpc::{Endpoint, Timestamp, Token};

use crate::actor::{Actor, RequestSend};
use crate::error::{ConnectSnafu, UnexpectedResponseSnafu};
use crate::response::ResponseResult;

g1_param::define!(request_timeout: Duration = Duration::from_secs(2));
g1_param::define!(blob_request_timeout: Duration = Duration::from_secs(8));

pub use crate::blob::RemoteBlob;
pub use crate::error::Error;
pub use crate::response::Response;

#[derive(Clone, Debug)]
pub struct RawClient {
    endpoint: Endpoint,
    request_send: RequestSend,
    cancel: Cancel,
}

pub type RawClientGuard = JoinGuard<Result<(), io::Error>>;

impl RawClient {
    pub fn connect(endpoint: Endpoint) -> Result<(Self, RawClientGuard), Error> {
        tracing::info!(%endpoint, "connect");

        let (request_send, request_recv) = mpsc::channel(16);

        let socket: Result<Socket, io::Error> = try {
            let mut socket = Socket::try_from(Context::new().socket(DEALER)?)?;
            socket.set_linger(0)?; // Do NOT block the program exit!
            socket.connect(&endpoint)?;
            socket
        };
        let socket = socket.context(ConnectSnafu)?;

        let guard = {
            let endpoint = endpoint.clone();
            RawClientGuard::spawn(move |cancel| {
                Actor::new(cancel, request_recv, socket.into())
                    .run()
                    .instrument(tracing::info_span!("ddcache/raw", %endpoint))
            })
        };

        Ok((
            Self {
                endpoint,
                request_send,
                cancel: guard.cancel_handle(),
            },
            guard,
        ))
    }

    pub fn disconnect(&self) {
        self.cancel.set();
    }

    pub fn endpoint(&self) -> Endpoint {
        self.endpoint.clone()
    }

    pub async fn cancel(&self, token: Token) -> Result<(), Error> {
        let response = self.request(ddcache_rpc::Request::Cancel(token)).await?;
        ensure!(response.is_none(), UnexpectedResponseSnafu);
        Ok(())
    }

    pub async fn read(&self, key: Bytes) -> ResponseResult {
        self.request(ddcache_rpc::Request::Read { key }).await
    }

    pub async fn read_metadata(&self, key: Bytes) -> ResponseResult {
        self.request(ddcache_rpc::Request::ReadMetadata { key })
            .await
    }

    pub async fn write(
        &self,
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
        &self,
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

    pub async fn remove(&self, key: Bytes) -> ResponseResult {
        self.request(ddcache_rpc::Request::Remove { key }).await
    }

    pub async fn pull(&self, key: Bytes) -> ResponseResult {
        self.request(ddcache_rpc::Request::Pull { key }).await
    }

    pub async fn push(
        &self,
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

    async fn request(&self, request: ddcache_rpc::Request) -> ResponseResult {
        let (response_send, response_recv) = oneshot::channel();
        self.request_send
            .send((request, response_send))
            .await
            .map_err(|_| Error::Stopped)?;
        response_recv.await.map_err(|_| Error::Stopped)?
    }
}
