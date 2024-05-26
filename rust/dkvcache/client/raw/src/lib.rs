pub mod concurrent;

mod actor;
mod error;

use std::io;
use std::sync::Arc;
use std::time::Duration;

use bytes::Bytes;
use snafu::prelude::*;
use tokio::sync::{mpsc, oneshot, watch};
use tracing::Instrument;
use uuid::Uuid;

use g1_tokio::sync::watch::Update;
use g1_tokio::task::{Cancel, JoinGuard};

use dkvcache_rpc::service::Server;
use dkvcache_rpc::{Request, Response, Timestamp};

use crate::actor::{Actor, RequestSend, ServerSend};
use crate::error::UnexpectedResponseSnafu;

g1_param::define!(request_timeout: Duration = Duration::from_secs(2));

g1_param::define!(idle_timeout: Duration = Duration::from_secs(120));

pub use crate::error::Error;

#[derive(Clone, Debug)]
pub struct RawClient {
    // TODO: Remove `Arc` after we upgrade `tokio` to v1.37.0.
    server_send: Arc<ServerSend>,
    request_send: RequestSend,
    cancel: Cancel,
}

pub type RawClientGuard = JoinGuard<Result<(), io::Error>>;

pub type ResponseResult = Result<Option<Response>, Error>;

impl RawClient {
    pub fn connect(id: Uuid, server: Server) -> (Self, RawClientGuard) {
        let (server_send, server_recv) = watch::channel(server);
        let (request_send, request_recv) = mpsc::channel(16);
        let guard = RawClientGuard::spawn(move |cancel| {
            Actor::new(cancel, server_recv, request_recv)
                .run()
                .instrument(tracing::info_span!("dkvcache/raw", %id))
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

    pub fn reconnect(&self, server: Server) {
        self.server_send.update(server);
    }

    pub fn disconnect(&self) {
        self.cancel.set();
    }

    async fn request(&self, request: Request) -> ResponseResult {
        let (response_send, response_recv) = oneshot::channel();
        self.request_send
            .send((request, response_send))
            .await
            .map_err(|_| Error::Stopped)?;
        response_recv.await.map_err(|_| Error::Stopped)?
    }

    pub async fn ping(&self) -> Result<(), Error> {
        let response = self.request(Request::Ping).await?;
        ensure!(response.is_none(), UnexpectedResponseSnafu);
        Ok(())
    }

    pub async fn get(&self, key: Bytes) -> ResponseResult {
        self.request(Request::Get { key }).await
    }

    pub async fn set(
        &self,
        key: Bytes,
        value: Bytes,
        expire_at: Option<Timestamp>,
    ) -> ResponseResult {
        self.request(Request::Set {
            key,
            value,
            expire_at,
        })
        .await
    }

    pub async fn update(
        &self,
        key: Bytes,
        value: Option<Bytes>,
        expire_at: Option<Option<Timestamp>>,
    ) -> ResponseResult {
        self.request(Request::Update {
            key,
            value,
            expire_at,
        })
        .await
    }

    pub async fn remove(&self, key: Bytes) -> ResponseResult {
        self.request(Request::Remove { key }).await
    }

    pub async fn pull(&self, key: Bytes) -> ResponseResult {
        self.request(Request::Pull { key }).await
    }

    pub async fn push(
        &self,
        key: Bytes,
        value: Bytes,
        expire_at: Option<Timestamp>,
    ) -> ResponseResult {
        self.request(Request::Push {
            key,
            value,
            expire_at,
        })
        .await
    }
}
