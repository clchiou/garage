use std::cmp;
use std::fs::File;
use std::os::fd::{AsFd, AsRawFd, BorrowedFd};

use bytes::Bytes;
use snafu::prelude::*;
use uuid::Uuid;

use etcd_pubsub::SubscriberError;

use ddcache_client_raw::{RawClient, concurrent};
use ddcache_client_service::Service;
use ddcache_rpc::service::PubSub;
use ddcache_rpc::{BlobMetadata, Timestamp};

use crate::error::{Error, RequestSnafu};

#[derive(Clone, Debug)]
pub struct Client(Service);

// For now we just make an alias.
pub use ddcache_client_service::ServiceGuard as ClientGuard;

macro_rules! metadata {
    ($response:ident $(,)?) => {
        $response
            .metadata
            .ok_or(ddcache_client_raw::Error::UnexpectedResponse)
    };
}

macro_rules! blob {
    ($response:ident $(,)?) => {
        $response
            .blob
            .ok_or(ddcache_client_raw::Error::UnexpectedResponse)
    };
}

impl Client {
    pub async fn spawn(pubsub: PubSub) -> Result<(Self, ClientGuard), SubscriberError> {
        let (service, guard) = Service::prepare(None, pubsub).await?.into();
        Ok((Self(service), guard))
    }

    fn all(&self) -> Result<impl Iterator<Item = (Uuid, RawClient)> + use<>, Error> {
        Ok(Self::unwrap_client(self.0.all()?))
    }

    fn find(&self, key: &[u8]) -> Result<impl Iterator<Item = (Uuid, RawClient)> + use<>, Error> {
        Ok(Self::unwrap_client(self.0.find(key, None)?))
    }

    fn unwrap_client(
        iter: impl IntoIterator<Item = (Uuid, Option<RawClient>)>,
    ) -> impl Iterator<Item = (Uuid, RawClient)> {
        iter.into_iter().map(|(id, client)| (id, client.unwrap()))
    }

    pub async fn read<F>(
        &self,
        key: Bytes,
        output: &mut F,
        size: Option<usize>,
    ) -> Result<Option<BlobMetadata>, Error>
    where
        F: AsFd + Send,
    {
        let servers = self.find(&key)?;
        let result: Result<Option<BlobMetadata>, ddcache_client_raw::Error> = try {
            let response = concurrent::request_any(servers, move |client| {
                let key = key.clone();
                async move { client.read(key).await }
            })
            .await?;

            let Some((_, _, response)) = response else {
                return Ok(None);
            };
            let metadata = metadata!(response)?;
            let blob = blob!(response)?;

            blob.read(output, cmp::min(metadata.size, size.unwrap_or(usize::MAX)))
                .await?;
            Some(metadata)
        };
        result.context(RequestSnafu)
    }

    pub async fn read_metadata(&self, key: Bytes) -> Result<Option<BlobMetadata>, Error> {
        let servers = self.find(&key)?;
        let result: Result<Option<BlobMetadata>, ddcache_client_raw::Error> = try {
            concurrent::request_any(servers, move |client| {
                let key = key.clone();
                async move { client.read_metadata(key).await }
            })
            .await?
            .map(|(_, _, response)| metadata!(response))
            .transpose()?
        };
        result.context(RequestSnafu)
    }

    pub async fn write_any<F>(
        &self,
        key: Bytes,
        metadata: Option<Bytes>,
        input: &mut F,
        size: usize,
        expire_at: Option<Timestamp>,
    ) -> Result<bool, Error>
    where
        F: AsFd + Send,
    {
        let servers = self.find(&key)?;
        let result: Result<bool, ddcache_client_raw::Error> = try {
            let response = concurrent::request_any(servers, move |client| {
                let key = key.clone();
                let metadata = metadata.clone();
                async move { client.write(key, metadata, size, expire_at).await }
            })
            .await?;

            let Some((_, _, response)) = response else {
                return Ok(false);
            };
            let blob = blob!(response)?;

            blob.write(input, size).await?;
            true
        };
        result.context(RequestSnafu)
    }

    /// Writes to all replicas and returns true if any of the writes succeed.
    pub async fn write_all(
        &self,
        key: Bytes,
        metadata: Option<Bytes>,
        input: &mut File,
        size: usize,
        expire_at: Option<Timestamp>,
    ) -> Result<bool, Error> {
        let fd = input.as_raw_fd();
        concurrent::request_all(
            self.find(&key)?,
            move |client| {
                let key = key.clone();
                let metadata = metadata.clone();
                async move { client.write(key, metadata, size, expire_at).await }
            },
            |response| async move {
                let blob = response
                    .blob
                    .ok_or(ddcache_client_raw::Error::UnexpectedResponse)?;
                let mut input = unsafe { BorrowedFd::borrow_raw(fd) };
                blob.write_file(&mut input, Some(0), size).await
            },
        )
        .await
        .context(RequestSnafu)
    }

    // Since a `write_metadata` request cannot be canceled, providing a `write_metadata_any`
    // function does not seem to offer much value.
    pub async fn write_metadata(
        &self,
        key: Bytes,
        metadata: Option<Option<Bytes>>,
        expire_at: Option<Option<Timestamp>>,
    ) -> Result<bool, Error> {
        concurrent::request_all(
            self.find(&key)?,
            move |client| {
                let key = key.clone();
                let metadata = metadata.clone();
                async move { client.write_metadata(key, metadata, expire_at).await }
            },
            |response| async move {
                let metadata = response
                    .metadata
                    .ok_or(ddcache_client_raw::Error::UnexpectedResponse)?;
                tracing::debug!(?metadata, "write_metadata");
                Ok(())
            },
        )
        .await
        .context(RequestSnafu)
    }

    /// Removes the blob from **all** shards (not just those required by the rendezvous hashing
    /// algorithm) to prevent the scenario where a blob is "accidentally" replicated to additional
    /// shards and later re-replicated.
    pub async fn remove(&self, key: Bytes) -> Result<bool, Error> {
        concurrent::request_all(
            self.all()?,
            move |client| {
                let key = key.clone();
                async move { client.remove(key.clone()).await }
            },
            |response| async move {
                let metadata = response
                    .metadata
                    .ok_or(ddcache_client_raw::Error::UnexpectedResponse)?;
                tracing::debug!(?metadata, "remove");
                Ok(())
            },
        )
        .await
        .context(RequestSnafu)
    }
}
