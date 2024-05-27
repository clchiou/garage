use std::sync::Arc;

use bytes::Bytes;
use snafu::prelude::*;
use tokio::sync::{broadcast::error::RecvError, mpsc, OwnedSemaphorePermit, Semaphore};
use tokio::task;
use tracing::Instrument;
use uuid::Uuid;

use etcd_pubsub::SubscriberError;
use g1_base::future::ReadyQueue;
use g1_tokio::task::{Cancel, JoinArray, JoinGuard, JoinQueue};

use dkvcache_client_raw::{concurrent, Error, RawClient};
use dkvcache_client_service::{NotConnectedError, Service, Update, UpdateRecv};
use dkvcache_rpc::service::{self, PubSub};
use dkvcache_storage::Storage;

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
    Storage { source: dkvcache_storage::Error },
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
                num_replicas: *dkvcache_rpc::num_replicas(),
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
                .instrument(tracing::info_span!("dkvcache-peer/pull", key = %key.escape_ascii()))
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
                .instrument(tracing::info_span!("dkvcache-peer/push", %peer_id))
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

        let response = concurrent::request(
            servers,
            |client| {
                let key = key.clone();
                async move { client.pull(key).await }
            },
            /* first */ true,
        )
        .await
        .context(RequestSnafu)?;

        if let Some(response) = response {
            self.storage
                .create(&key, &response.value, response.expire_at)
                .context(StorageSnafu)?;
        }
        Ok(())
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

        let mut num_push = 0;
        let queue = ReadyQueue::new();
        let concurrency = Arc::new(Semaphore::new(self.push_concurrency));
        tokio::try_join!(
            async {
                for key in self.storage.scan(/* most_recent */ true) {
                    let key = key.context(StorageSnafu)?;

                    // Check whether the target server is not a designated replica of `key`.
                    servers.sort_by_key(service::rendezvous_sorting_by_key(&key, |(id, _)| *id));
                    if !servers
                        .iter()
                        .take(self.num_replicas)
                        .any(|(id, _)| id == &peer_id)
                    {
                        continue;
                    }

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
        _permit: OwnedSemaphorePermit,
        key: Bytes,
    ) -> Result<bool, HandlerError> {
        let Some(entry) = self.storage.peek(&key).context(StorageSnafu)? else {
            return Ok(false);
        };
        tracing::debug!(key = %key.escape_ascii());
        Ok(client
            .push(key, entry.value, entry.expire_at)
            .await
            .context(RequestSnafu)?
            .is_none())
    }

    async fn cleanup(&self) -> Result<(), HandlerError> {
        // This seems to warrant using `spawn_blocking`.
        let handler = self.clone();
        task::spawn_blocking(move || handler.cleanup_blocking())
            .await
            .unwrap()
    }

    fn cleanup_blocking(&self) -> Result<(), HandlerError> {
        let mut keys = Vec::new();
        let mut servers = self.service.all()?;
        for key in self.storage.scan(/* most_recent */ false) {
            let key = key.context(StorageSnafu)?;
            // Check whether we are not a designated replica of `key`.
            servers.sort_by_key(service::rendezvous_sorting_by_key(&key, |(id, _)| *id));
            if !servers
                .iter()
                .take(self.num_replicas)
                .any(|(id, _)| id == &self.self_id)
            {
                keys.push(key);
            }
        }
        let num_cleanup = self
            .storage
            .remove_many(keys.iter().map(|key| key.as_ref()))
            .context(StorageSnafu)?;
        tracing::info!(num_cleanup);
        Ok(())
    }
}
