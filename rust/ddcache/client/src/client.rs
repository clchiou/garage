use std::cmp;
use std::fs::File;
use std::io;
use std::os::fd::{AsFd, AsRawFd, BorrowedFd};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};

use bytes::Bytes;
use futures::stream::StreamExt;
use snafu::prelude::*;
use uuid::Uuid;

use g1_base::future::ReadyQueue;
use g1_base::sync::MutexExt;
use g1_tokio::sync::oneway::Flag;
use g1_tokio::task::{Cancel, JoinGuard, JoinQueue};

use ddcache_client_raw::{RawClient, RawClientGuard};
use ddcache_rpc::service::{self, Event, PubSub, Subscriber};
use ddcache_rpc::{BlobMetadata, Timestamp};

use crate::error::{Error, ProtocolSnafu};
use crate::route::RouteMap;

#[derive(Clone, Debug)]
pub struct Client {
    service_ready: Arc<Flag>,
    routes: Arc<Mutex<RouteMap>>,
    num_replicas: usize,
}

pub type ClientGuard = JoinGuard<Result<(), io::Error>>;

#[derive(Debug)]
struct Actor {
    cancel: Cancel,
    service_ready: Arc<Flag>,
    pubsub: PubSub,
    routes: Arc<Mutex<RouteMap>>,
    tasks: JoinQueue<Result<(), io::Error>>,
}

// le = last error

macro_rules! le_push {
    ($message:tt, $last_error:ident, $id:expr, $error:expr) => {
        if let Some((id, error)) = $last_error.replace(($id, Error::Protocol { source: $error })) {
            tracing::warn!(%id, %error, $message);
        }
    };
}

macro_rules! le_finish {
    ($message:tt, $last_error:ident, $succeed:expr) => {
        if let Some((id, error)) = $last_error {
            if $succeed {
                tracing::warn!(%id, %error, $message);
            } else {
                return Err(error);
            }
        }
    };
}

impl Client {
    pub fn spawn() -> (Self, ClientGuard) {
        let service_ready = Arc::new(Flag::new());
        let routes = Arc::new(Mutex::new(RouteMap::new()));
        (
            Self {
                service_ready: service_ready.clone(),
                routes: routes.clone(),
                num_replicas: *ddcache_rpc::num_replicas(),
            },
            ClientGuard::spawn(move |cancel| Actor::new(cancel, service_ready, routes).run()),
        )
    }

    pub async fn service_ready(&self) {
        self.service_ready.wait().await
    }

    fn all(&self) -> Result<Vec<(Uuid, RawClient)>, Error> {
        self.routes.must_lock().all()
    }

    fn find(&self, key: &[u8]) -> Result<Vec<(Uuid, RawClient)>, Error> {
        self.routes.must_lock().find(key, self.num_replicas)
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
        let queue = ReadyQueue::new();
        let first = Arc::new(AtomicBool::new(true));
        for (id, shard) in self.find(&key)? {
            let key = key.clone();
            let first = first.clone();
            assert!(queue
                .push(async move {
                    let response = shard.read(key).await;
                    if !matches!(response, Ok(Some(_))) || first.swap(false, Ordering::SeqCst) {
                        return (id, response);
                    }

                    let response = shard
                        .cancel(response.unwrap().unwrap().blob.unwrap().token())
                        .await
                        .map(|()| None);
                    (id, response)
                })
                .is_ok());
        }
        queue.close();

        let mut succeed = false;
        let mut last_error = None;
        let mut metadata = None;

        while let Some((id, response)) = queue.pop_ready().await {
            let response = match response {
                Ok(Some(response)) => response,
                Ok(None) => continue,
                Err(error) => {
                    le_push!("read", last_error, id, error);
                    continue;
                }
            };

            let size = cmp::min(
                response.metadata.as_ref().unwrap().size,
                size.unwrap_or(usize::MAX),
            );
            metadata = Some(response.metadata.unwrap());

            match response.blob.unwrap().read(output, size).await {
                Ok(()) => succeed = true,
                Err(error) => le_push!("read", last_error, id, error),
            }

            join_cancels(queue);
            break;
        }

        le_finish!("read", last_error, succeed);
        Ok(metadata)
    }

    pub async fn read_metadata(&self, key: Bytes) -> Result<Option<BlobMetadata>, Error> {
        let queue = ReadyQueue::new();
        for (id, shard) in self.find(&key)? {
            let key = key.clone();
            assert!(queue
                .push(async move {
                    let response = shard.read_metadata(key).await;
                    (id, response)
                })
                .is_ok());
        }
        queue.close();

        let mut metadata = None;
        let mut last_error = None;

        while let Some((id, response)) = queue.pop_ready().await {
            let response = match response {
                Ok(Some(response)) => response,
                Ok(None) => continue,
                Err(error) => {
                    le_push!("read_metadata", last_error, id, error);
                    continue;
                }
            };
            metadata = Some(response.metadata.unwrap());
            break;
        }

        le_finish!("read_metadata", last_error, metadata.is_some());
        Ok(metadata)
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
        let queue = ReadyQueue::new();
        let first = Arc::new(AtomicBool::new(true));
        for (id, shard) in self.find(&key)? {
            let key = key.clone();
            let metadata = metadata.clone();
            let first = first.clone();
            assert!(queue
                .push(async move {
                    let response = shard.write(key, metadata, size, expire_at).await;
                    if !matches!(response, Ok(Some(_))) || first.swap(false, Ordering::SeqCst) {
                        return (id, response);
                    }

                    let response = shard
                        .cancel(response.unwrap().unwrap().blob.unwrap().token())
                        .await
                        .map(|()| None);
                    (id, response)
                })
                .is_ok());
        }
        queue.close();

        let mut succeed = false;
        let mut last_error = None;

        while let Some((id, response)) = queue.pop_ready().await {
            let response = match response {
                Ok(Some(response)) => response,
                Ok(None) => continue,
                Err(error) => {
                    le_push!("write_any", last_error, id, error);
                    continue;
                }
            };

            match response.blob.unwrap().write(input, size).await {
                Ok(()) => succeed = true,
                Err(error) => le_push!("write_any", last_error, id, error),
            }

            join_cancels(queue);
            break;
        }

        le_finish!("write_any", last_error, succeed);
        Ok(succeed)
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
        let queue = ReadyQueue::new();
        let fd = input.as_raw_fd();
        for (id, shard) in self.find(&key)? {
            let key = key.clone();
            let metadata = metadata.clone();
            assert!(queue
                .push(async move {
                    let response = match shard.write(key, metadata, size, expire_at).await {
                        Ok(Some(response)) => response,
                        Ok(None) => return (id, Ok(false)),
                        Err(error) => return (id, Err(error)),
                    };

                    let mut input = unsafe { BorrowedFd::borrow_raw(fd) };
                    match response
                        .blob
                        .unwrap()
                        .write_file(&mut input, Some(0), size)
                        .await
                    {
                        Ok(()) => (id, Ok(true)),
                        Err(error) => (id, Err(error)),
                    }
                })
                .is_ok());
        }
        queue.close();

        let mut succeed = false;
        let mut last_error = None;

        while let Some((id, response)) = queue.pop_ready().await {
            match response {
                Ok(true) => succeed = true,
                Ok(false) => {}
                Err(error) => le_push!("write_all", last_error, id, error),
            }
        }

        le_finish!("write_all", last_error, succeed);
        Ok(succeed)
    }

    // Since a `write_metadata` request cannot be canceled, providing a `write_metadata_any`
    // function does not seem to offer much value.
    pub async fn write_metadata(
        &self,
        key: Bytes,
        metadata: Option<Option<Bytes>>,
        expire_at: Option<Option<Timestamp>>,
    ) -> Result<bool, Error> {
        let queue = ReadyQueue::new();
        for (id, shard) in self.find(&key)? {
            let key = key.clone();
            let metadata = metadata.clone();
            assert!(queue
                .push(async move {
                    let response = shard.write_metadata(key, metadata, expire_at).await;
                    (id, response)
                })
                .is_ok());
        }
        queue.close();

        let mut succeed = false;
        let mut last_error = None;

        while let Some((id, response)) = queue.pop_ready().await {
            match response {
                Ok(Some(response)) => {
                    tracing::debug!(%id, ?response, "write_metadata");
                    succeed = true;
                }
                Ok(None) => {}
                Err(error) => le_push!("write_metadata", last_error, id, error),
            }
        }

        le_finish!("write_metadata", last_error, succeed);
        Ok(succeed)
    }

    /// Removes the blob from **all** shards (not just those required by the rendezvous hashing
    /// algorithm) to prevent the scenario where a blob is "accidentally" replicated to additional
    /// shards and later re-replicated.
    pub async fn remove(&self, key: Bytes) -> Result<bool, Error> {
        let queue = ReadyQueue::new();
        for (id, shard) in self.all()? {
            let key = key.clone();
            assert!(queue
                .push(async move {
                    let response = shard.remove(key).await;
                    (id, response)
                })
                .is_ok());
        }
        queue.close();

        let mut succeed = false;
        let mut last_error = None;

        while let Some((id, response)) = queue.pop_ready().await {
            match response {
                Ok(Some(response)) => {
                    tracing::debug!(%id, ?response, "remove");
                    succeed = true;
                }
                Ok(None) => {}
                Err(error) => le_push!("remove", last_error, id, error),
            }
        }

        le_finish!("remove", last_error, succeed);
        Ok(succeed)
    }
}

fn join_cancels<T>(queue: ReadyQueue<(Uuid, Result<Option<T>, ddcache_client_raw::Error>)>)
where
    T: Send + 'static,
{
    // Do not block on joining the `shard.cancel()` futures.
    tokio::spawn(async move {
        while let Some((id, response)) = queue.pop_ready().await {
            match response.context(ProtocolSnafu) {
                Ok(Some(_)) => std::panic!("expect Ok(None) or Err"),
                Ok(None) => {}
                Err(error) => tracing::debug!(%id, %error, "cancel"),
            }
        }
    });
}

impl Actor {
    fn new(cancel: Cancel, service_ready: Arc<Flag>, routes: Arc<Mutex<RouteMap>>) -> Self {
        Self {
            cancel,
            service_ready,
            pubsub: service::pubsub(),
            routes,
            tasks: JoinQueue::new(),
        }
    }

    async fn run(self) -> Result<(), io::Error> {
        let mut subscriber = self.init_subscriber().await?;
        self.service_ready.set();

        loop {
            tokio::select! {
                () = self.cancel.wait() => break,

                event = subscriber.next() => {
                    match event {
                        Some(Ok(event)) => self.handle_subscribe(event),
                        Some(Err(error)) => {
                            tracing::warn!(%error, "subscriber");
                            // TODO: Wait for a backoff period before resubscribing.
                            subscriber = self.init_subscriber().await?;
                        }
                        None => {
                            tracing::warn!("subscriber stop unexpectedly");
                            // TODO: Wait for a backoff period before resubscribing.
                            subscriber = self.init_subscriber().await?;
                        }
                    }
                }

                guard = self.tasks.join_next() => {
                    let Some(guard) = guard else { break };
                    self.handle_task(guard);
                }
            }
        }

        self.tasks.cancel();
        while let Some(guard) = self.tasks.join_next().await {
            self.handle_task(guard);
        }

        Ok(())
    }

    async fn init_subscriber(&self) -> Result<Subscriber, io::Error> {
        let subscriber = self.pubsub.subscribe().await.map_err(io::Error::other)?;

        let servers = self.pubsub.scan().await.map_err(io::Error::other)?;
        {
            let mut routes = self.routes.must_lock();
            for (id, server) in servers {
                routes.connect(&self.tasks, id, server);
            }
        }

        Ok(subscriber)
    }

    fn handle_subscribe(&self, event: Event) {
        let mut routes = self.routes.must_lock();
        match event {
            Event::Create((id, server))
            | Event::Update {
                id, new: server, ..
            } => routes.connect(&self.tasks, id, server),
            Event::Delete((id, _)) => routes.disconnect(id),
        }
    }

    fn handle_task(&self, mut guard: RawClientGuard) {
        let (id, _) = self.routes.must_lock().remove(guard.id()).unwrap();
        match guard.take_result() {
            Ok(Ok(())) => {}
            Ok(Err(error)) => tracing::warn!(%id, %error, "shard error"),
            Err(error) => tracing::warn!(%id, %error, "shard task error"),
        }
    }
}
