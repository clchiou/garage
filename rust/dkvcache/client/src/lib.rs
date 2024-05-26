use bytes::Bytes;
use snafu::prelude::*;
use uuid::Uuid;

use etcd_pubsub::SubscriberError;

use dkvcache_client_raw::{concurrent, RawClient};
use dkvcache_client_service::{NotConnectedError, Service};
use dkvcache_rpc::service::PubSub;
use dkvcache_rpc::Response;

pub use dkvcache_rpc::Timestamp;

#[derive(Debug, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    #[snafu(display("not connected to any server"))]
    NotConnected,
    #[snafu(display("request error: {source}"))]
    Request { source: dkvcache_client_raw::Error },
}

impl From<NotConnectedError> for Error {
    fn from(_: NotConnectedError) -> Self {
        Self::NotConnected
    }
}

#[derive(Clone, Debug)]
pub struct Client(Service);

// For now we just make an alias.
pub use dkvcache_client_service::ServiceGuard as ClientGuard;

impl Client {
    pub async fn spawn(pubsub: PubSub) -> Result<(Self, ClientGuard), SubscriberError> {
        let (service, guard) = Service::prepare(None, pubsub).await?.into();
        Ok((Self(service), guard))
    }

    fn all(&self) -> Result<impl Iterator<Item = (Uuid, RawClient)>, Error> {
        Ok(Self::unwrap_client(self.0.all()?))
    }

    fn find(&self, key: &[u8]) -> Result<impl Iterator<Item = (Uuid, RawClient)>, Error> {
        Ok(Self::unwrap_client(self.0.find(key, None)?))
    }

    fn unwrap_client(
        iter: impl IntoIterator<Item = (Uuid, Option<RawClient>)>,
    ) -> impl Iterator<Item = (Uuid, RawClient)> {
        iter.into_iter().map(|(id, client)| (id, client.unwrap()))
    }

    pub async fn get(&self, key: Bytes) -> Result<Option<Response>, Error> {
        concurrent::request(
            self.find(&key)?,
            move |client| {
                let key = key.clone();
                async move { client.get(key).await }
            },
            /* first */ true,
        )
        .await
        .context(RequestSnafu)
    }

    pub async fn set(
        &self,
        key: Bytes,
        value: Bytes,
        expire_at: Option<Timestamp>,
    ) -> Result<bool, Error> {
        concurrent::request(
            self.find(&key)?,
            move |client| {
                let key = key.clone();
                let value = value.clone();
                async move { client.set(key, value, expire_at).await }
            },
            /* first */ false,
        )
        .await
        .map(|response| response.is_none()) // Returns whether the entry was newly inserted.
        .context(RequestSnafu)
    }

    pub async fn update(
        &self,
        key: Bytes,
        value: Option<Bytes>,
        expire_at: Option<Option<Timestamp>>,
    ) -> Result<bool, Error> {
        concurrent::request(
            self.find(&key)?,
            move |client| {
                let key = key.clone();
                let value = value.clone();
                async move { client.update(key, value, expire_at).await }
            },
            /* first */ false,
        )
        .await
        .map(|response| response.is_some())
        .context(RequestSnafu)
    }

    /// Removes the entry from **all** servers (not just those required by the rendezvous hashing
    /// algorithm) to prevent the scenario where an entry is "accidentally" replicated to
    /// additional servers and later re-replicated.
    pub async fn remove(&self, key: Bytes) -> Result<bool, Error> {
        concurrent::request(
            self.all()?,
            move |client| {
                let key = key.clone();
                async move { client.remove(key).await }
            },
            /* first */ false,
        )
        .await
        .map(|response| response.is_some())
        .context(RequestSnafu)
    }
}
