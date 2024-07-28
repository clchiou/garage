#![feature(try_blocks)]

use std::io;
use std::sync::Arc;

use bytes::Bytes;
use snafu::prelude::*;
use tokio::sync::{broadcast::error::RecvError, mpsc, OwnedSemaphorePermit, Semaphore};
use tracing::Instrument;
use uuid::Uuid;

use etcd_pubsub::SubscriberError;
use g1_base::future::ReadyQueue;
use g1_tokio::task::{Cancel, JoinArray, JoinGuard, JoinQueue};

use ddcache_client_raw::{concurrent, Error, RawClient};
use ddcache_client_service::{NotConnectedError, Service, Update, UpdateRecv};
use ddcache_rpc::service::{self, PubSub};
use ddcache_storage::Storage;

g1_param::define!(push_concurrency: usize = 32);

#[derive(Clone, Debug)]
pub struct Peer {
    pull_send: PullSend,
}

pub type PeerGuard = JoinArray<Result<(), SubscriberError>, 2>;

#[derive(Debug)]
struct Actor {
    cancel: Cancel,

    pull_recv: PullRecv,
    update_recv: UpdateRecv,

    handler: Handler,
    tasks: JoinQueue<Result<(), HandlerError>>,
}

type PullRecv = mpsc::Receiver<Bytes>;
type PullSend = mpsc::Sender<Bytes>;

#[derive(Clone, Debug)]
struct Handler {
    self_id: Uuid,
    num_replicas: usize,
    push_concurrency: usize,

    service: Service,
    storage: Storage,
}

#[derive(Debug, Snafu)]
enum HandlerError {
    #[snafu(display("not connected to any peer server"))]
    NotConnected,
    #[snafu(display("request error: {source}"))]
    Request { source: Error },
    #[snafu(display("storage error: {source}"))]
    Storage { source: io::Error },
}

impl From<NotConnectedError> for HandlerError {
    fn from(_: NotConnectedError) -> Self {
        Self::NotConnected
    }
}

impl Peer {
    pub async fn spawn(
        self_id: Uuid,
        pubsub: PubSub,
        storage: Storage,
    ) -> Result<(Self, PeerGuard), SubscriberError> {
        let (pull_send, pull_recv) = mpsc::channel(16);

        let spawn = Service::prepare(Some(self_id), pubsub).await?;
        let update_recv = spawn.subscribe();
        let (service, service_guard) = spawn.into();

        let peer_guard = JoinGuard::spawn(move |cancel| {
            Actor::new(cancel, self_id, pull_recv, update_recv, service, storage).run()
        });

        Ok((
            Self { pull_send },
            JoinArray::new([peer_guard, service_guard]),
        ))
    }

    pub async fn pull(&self, key: Bytes) {
        let _ = self.pull_send.send(key).await;
    }

    pub fn try_pull(&self, key: Bytes) {
        let _ = self.pull_send.try_send(key);
    }
}

impl Actor {
    fn new(
        cancel: Cancel,
        self_id: Uuid,
        pull_recv: PullRecv,
        update_recv: UpdateRecv,
        service: Service,
        storage: Storage,
    ) -> Self {
        Self {
            cancel,
            pull_recv,
            update_recv,
            handler: Handler {
                self_id,
                num_replicas: *ddcache_rpc::num_replicas(),
                push_concurrency: *crate::push_concurrency(),
                service,
                storage,
            },
            tasks: JoinQueue::new(),
        }
    }

    async fn run(mut self) -> Result<(), SubscriberError> {
        loop {
            tokio::select! {
                () = self.cancel.wait() => break,

                key = self.pull_recv.recv() => {
                    let Some(key) = key else { break };
                    self.handle_pull(key);
                }

                update = self.update_recv.recv() => {
                    match update {
                        Ok(update) => self.handle_update(update),
                        Err(RecvError::Lagged(num_skipped)) => {
                            // TODO: Should we return an error instead?
                            tracing::warn!(num_skipped, "lag behind on service updates");
                        }
                        Err(RecvError::Closed) => break,
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

    fn handle_pull(&self, key: Bytes) {
        let handler = self.handler.clone();
        assert!(self
            .tasks
            .push(JoinGuard::spawn(move |cancel| {
                {
                    let key = key.clone();
                    async move {
                        tokio::select! {
                            () = cancel.wait() => Ok(()),
                            result = handler.pull(key) => result,
                        }
                    }
                }
                .instrument(tracing::info_span!("ddcache-peer/pull", key = %key.escape_ascii()))
            }))
            .is_ok());
    }

    fn handle_update(&self, update: Update) {
        // TODO: Also consider doing a `push` in the `Update::Stop` case.
        let Update::Start(peer_id) = update else {
            return;
        };
        if peer_id == self.handler.self_id {
            return;
        }
        let handler = self.handler.clone();
        assert!(self
            .tasks
            .push(JoinGuard::spawn(move |cancel| {
                async move {
                    tokio::select! {
                        () = cancel.wait() => Ok(()),
                        result = async {
                            handler.push(peer_id).await?;
                            handler.cleanup().await
                        } => result,
                    }
                }
                .instrument(tracing::info_span!("ddcache-peer/push", %peer_id))
            }))
            .is_ok());
    }

    fn handle_task(&self, mut guard: JoinGuard<Result<(), HandlerError>>) {
        match guard.take_result() {
            Ok(Ok(())) => {}
            Ok(Err(error)) => tracing::warn!(%error, "peer handler error"),
            Err(error) => tracing::warn!(%error, "peer handler task error"),
        }
    }
}

macro_rules! metadata {
    ($response:ident $(,)?) => {
        $response.metadata.ok_or(Error::UnexpectedResponse)
    };
}

macro_rules! blob {
    ($response:ident $(,)?) => {
        $response.blob.ok_or(Error::UnexpectedResponse)
    };
}

impl Handler {
    async fn pull(&self, key: Bytes) -> Result<(), HandlerError> {
        let mut servers = self
            .service
            // We exploit the fact that a blob might be replicated to additional peers.
            .find(&key, Some(self.num_replicas + 1))?;

        match servers
            .iter()
            .position(|(peer_id, _)| peer_id == &self.self_id)
        {
            Some(i) if i < self.num_replicas => {
                assert!(servers.remove(i).1.is_none());
            }
            _ => {
                // We are not a designated replica of `key`.
                return Ok(());
            }
        }
        let servers = servers
            .into_iter()
            .map(|(id, client)| (id, client.unwrap()));

        let result: Result<_, Error> = try {
            let response = concurrent::request_any(servers, |client| {
                let key = key.clone();
                async move { client.pull(key).await }
            })
            .await?;

            let Some((id, client, response)) = response else {
                return Ok(());
            };
            let metadata = metadata!(response)?;
            let blob = blob!(response)?;

            let Some(mut writer) = self.storage.write_new(key) else {
                if let Err(error) = client.cancel(blob.token()).await {
                    tracing::warn!(%id, %error, "cancel");
                }
                return Ok(());
            };

            writer.set_metadata(metadata.metadata);
            writer.set_expire_at(metadata.expire_at);

            let output = match writer.open() {
                Ok(output) => output,
                Err(error) => {
                    drop(writer);
                    if let Err(error) = client.cancel(blob.token()).await {
                        tracing::warn!(%id, %error, "cancel");
                    }
                    return Err(HandlerError::Storage { source: error });
                }
            };

            blob.read(output, metadata.size).await?;

            writer
        };
        result.context(RequestSnafu)?.commit().context(StorageSnafu)
    }

    async fn push(&self, peer_id: Uuid) -> Result<(), HandlerError> {
        if peer_id == self.self_id {
            return Ok(());
        }

        let mut servers = self.service.all()?;

        let Some(client) = servers
            .iter()
            .find_map(|(id, client)| (id == &peer_id).then(|| client.clone().unwrap()))
        else {
            // We are not connected to the target server.
            return Ok(());
        };

        // Start with the most recent keys.
        let keys = self.storage.keys().into_iter().rev();

        let keys = keys.filter(move |key| {
            // Check whether the target server is a designated replica of `key`.
            servers.sort_by_key(service::rendezvous_sorting_by_key(key, |(id, _)| *id));
            servers
                .iter()
                .take(self.num_replicas)
                .any(|(id, _)| id == &peer_id)
        });

        let mut num_push = 0;
        let queue = ReadyQueue::new();
        let concurrency = Arc::new(Semaphore::new(self.push_concurrency));
        tokio::try_join!(
            async {
                for key in keys {
                    let permit = concurrency.clone().acquire_owned().await.unwrap();
                    let handler = self.clone();
                    let client = client.clone();
                    assert!(queue
                        .push(async move { handler.push_key(client, permit, key).await })
                        .is_ok());
                }
                queue.close();
                Ok::<_, HandlerError>(())
            },
            async {
                while let Some(result) = queue.pop_ready().await {
                    if result? {
                        num_push += 1;
                    }
                }
                Ok(())
            },
        )?;
        tracing::info!(num_push);
        Ok(())
    }

    async fn push_key(
        &self,
        client: RawClient,
        permit: OwnedSemaphorePermit,
        key: Bytes,
    ) -> Result<bool, HandlerError> {
        let Some(reader) = self.storage.peek(key.clone()).await else {
            return Ok(false);
        };
        let size = usize::try_from(reader.size()).unwrap();

        tracing::debug!(key = %key.escape_ascii());
        let result: Result<bool, Error> = try {
            let Some(response) = client
                .push(key, reader.metadata(), size, reader.expire_at())
                .await?
            else {
                return Ok(false);
            };
            let blob = blob!(response)?;

            let mut input = match reader.open() {
                Ok(input) => input,
                Err(error) => {
                    drop(reader);
                    drop(permit);
                    if let Err(error) = client.cancel(blob.token()).await {
                        tracing::warn!(%error, "cancel");
                    }
                    return Err(HandlerError::Storage { source: error });
                }
            };

            blob.write_file(&mut input, None, size).await?;

            true
        };
        result.context(RequestSnafu)
    }

    async fn cleanup(&self) -> Result<(), HandlerError> {
        let mut servers = self.service.all()?;
        let keys = self.storage.keys().into_iter().filter(move |key| {
            // Check whether we are not a designated replica of `key`.
            servers.sort_by_key(service::rendezvous_sorting_by_key(key, |(id, _)| *id));
            !servers
                .iter()
                .take(self.num_replicas)
                .any(|(id, _)| id == &self.self_id)
        });

        let mut num_cleanup = 0;
        for key in keys {
            self.storage.remove(key).await.context(StorageSnafu)?;
            num_cleanup += 1;
        }
        tracing::info!(num_cleanup);
        Ok(())
    }
}
