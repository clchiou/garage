#![feature(assert_matches)]

use std::assert_matches::assert_matches;
use std::collections::HashMap;
use std::io;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use futures::stream::StreamExt;
use snafu::prelude::*;
use tokio::sync::{broadcast, OwnedSemaphorePermit, Semaphore};
use tokio::task;
use tokio::time::{self, Instant};
use uuid::Uuid;

use etcd_pubsub::SubscriberError;
use g1_base::collections::HashBasedBiTable;
use g1_base::fmt::{DebugExt, InsertPlaceholder};
use g1_base::iter::IteratorExt;
use g1_base::sync::MutexExt;
use g1_tokio::task::{Cancel, JoinGuard, JoinQueue};
use g1_tokio::time::queue::naive::FixedDelayQueue;

use dkvcache_client_raw::{RawClient, RawClientGuard};
use dkvcache_rpc::service::{self, Event, PubSub, Server, Subscriber};

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("not connected to any server"))]
pub struct NotConnectedError;

#[derive(Clone, Debug)]
pub struct Service {
    servers: Arc<ServerMap>,
    num_replicas: usize,
    update_recv: Arc<UpdateRecv>,
    _dropped: Arc<OwnedSemaphorePermit>,
}

pub type ServiceGuard = JoinGuard<Result<(), SubscriberError>>;

#[derive(DebugExt)]
pub struct ServiceSpawn {
    self_id: Option<Uuid>,
    pubsub: PubSub,
    #[debug(with = InsertPlaceholder)]
    subscriber: Subscriber,
    servers: Vec<(Uuid, Server)>,
    update_recv: UpdateRecv,
    update_send: UpdateSend,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Update {
    Start(Uuid),
    Stop(Uuid),
}

pub type UpdateRecv = broadcast::Receiver<Update>;
pub type UpdateSend = broadcast::Sender<Update>;

#[derive(DebugExt)]
struct Actor {
    cancel: Cancel,
    dropped: Arc<Semaphore>,
    pubsub: PubSub,
    #[debug(with = InsertPlaceholder)]
    subscriber: Subscriber,
    servers: Arc<ServerMap>,

    // I observed that our etcd cluster is quite unstable, likely due to running on hardware that
    // falls below the recommended specifications.  To mitigate this issue, we will only disconnect
    // from a server when we have not seen it for a while.
    last_seen: HashMap<Uuid, Instant>,
    will_disconnect: FixedDelayQueue<Uuid>,
}

#[derive(Debug)]
struct ServerMap {
    servers: Mutex<ServerTable>,
    tasks: JoinQueue<Result<(), io::Error>>,
    update_send: UpdateSend,
}

type ServerTable = HashBasedBiTable<Uuid, Option<task::Id>, Option<RawClient>>;

const DISCONNECT_BEFORE: Duration = Duration::from_secs(20);

impl Service {
    pub async fn prepare(
        self_id: Option<Uuid>,
        pubsub: PubSub,
    ) -> Result<ServiceSpawn, SubscriberError> {
        let subscriber = pubsub.subscribe().await?;
        let servers = pubsub.scan().await?;
        let (update_send, update_recv) = broadcast::channel(32);
        Ok(ServiceSpawn {
            self_id,
            pubsub,
            subscriber,
            servers,
            update_send,
            update_recv,
        })
    }
}

impl ServiceSpawn {
    pub fn subscribe(&self) -> UpdateRecv {
        self.update_recv.resubscribe()
    }
}

impl From<ServiceSpawn> for (Service, ServiceGuard) {
    fn from(spawn: ServiceSpawn) -> Self {
        let ServiceSpawn {
            self_id,
            pubsub,
            subscriber,
            servers,
            update_send,
            update_recv,
        } = spawn;
        let servers = Arc::new(ServerMap::new(self_id, servers, update_send));
        let dropped = Arc::new(Semaphore::new(1));
        let _dropped = Arc::new(dropped.clone().try_acquire_owned().unwrap());
        (
            Service {
                servers: servers.clone(),
                num_replicas: *dkvcache_rpc::num_replicas(),
                update_recv: Arc::new(update_recv),
                _dropped,
            },
            ServiceGuard::spawn(move |cancel| {
                Actor::new(cancel, dropped, pubsub, subscriber, servers).run()
            }),
        )
    }
}

impl Service {
    pub fn subscribe(&self) -> UpdateRecv {
        self.update_recv.resubscribe()
    }

    pub fn all(&self) -> Result<Vec<(Uuid, Option<RawClient>)>, NotConnectedError> {
        self.servers.all()
    }

    /// Finds servers via the Rendezvous Hashing algorithm.
    pub fn find(
        &self,
        key: &[u8],
        num_replicas: Option<usize>,
    ) -> Result<Vec<(Uuid, Option<RawClient>)>, NotConnectedError> {
        self.servers
            .find(key, num_replicas.unwrap_or(self.num_replicas))
    }
}

impl Actor {
    fn new(
        cancel: Cancel,
        dropped: Arc<Semaphore>,
        pubsub: PubSub,
        subscriber: Subscriber,
        servers: Arc<ServerMap>,
    ) -> Self {
        let now = Instant::now();
        let last_seen = HashMap::from_iter(servers.servers.must_lock().rows().map(|id| (*id, now)));
        Self {
            cancel,
            dropped,
            pubsub,
            subscriber,
            servers,

            last_seen,
            // TODO: Consider making this delay configurable.
            will_disconnect: FixedDelayQueue::new(DISCONNECT_BEFORE),
        }
    }

    async fn run(mut self) -> Result<(), SubscriberError> {
        loop {
            tokio::select! {
                () = self.cancel.wait() => break,

                // Exit when all `Service` instances are dropped.
                _ = self.dropped.clone().acquire_owned() => break,

                event = self.subscriber.next() => {
                    match event {
                        Some(Ok(event)) => self.handle_subscriber_event(event),
                        Some(Err(error)) => {
                            tracing::warn!(%error, "subscriber");
                            self.reinit_subscriber().await?;
                        }
                        None => {
                            tracing::warn!("unexpected subscriber stop");
                            self.reinit_subscriber().await?;
                        }
                    }
                }

                Some(id) = self.will_disconnect.pop() => {
                    // Let us try updating `last_seen` one last time.
                    self.update_last_seen(&self.pubsub.scan().await?);

                    if self
                        .last_seen
                        .get(&id)
                        .map_or(true, |last_seen| last_seen.elapsed() > DISCONNECT_BEFORE)
                    {
                        tracing::warn!(%id, "disconnect unseen server");
                        self.servers.disconnect(id);
                    }
                }

                guard = self.servers.tasks.join_next() => {
                    let Some(guard) = guard else { break };
                    self.servers.handle_task(guard);
                }
            }
        }

        self.servers.tasks.cancel();
        while let Some(guard) = self.servers.tasks.join_next().await {
            self.servers.handle_task(guard);
        }

        Ok(())
    }

    async fn reinit_subscriber(&mut self) -> Result<(), SubscriberError> {
        const NUM_RETRIES: usize = 4;
        let mut backoff = Duration::from_secs(1);
        for retry in 0..NUM_RETRIES {
            match self.pubsub.subscribe().await {
                Ok(subscriber) => {
                    self.subscriber = subscriber;
                    let servers = self.pubsub.scan().await?;
                    self.update_last_seen(&servers);
                    self.servers.connect_many(servers);
                    return Ok(());
                }
                Err(error) => {
                    if retry + 1 == NUM_RETRIES {
                        return Err(error);
                    } else {
                        tracing::warn!(retry, %error, "reinit subscriber");
                        time::sleep(backoff).await;
                        backoff *= 2;
                    }
                }
            }
        }
        std::unreachable!()
    }

    fn handle_subscriber_event(&mut self, event: Event) {
        match event {
            Event::Create((id, server))
            | Event::Update {
                id, new: server, ..
            } => {
                self.last_seen.insert(id, Instant::now());
                self.servers.connect(id, server);
            }
            Event::Delete((id, _)) => {
                self.will_disconnect.push(id);
            }
        }
    }

    fn update_last_seen(&mut self, servers: &[(Uuid, Server)]) {
        let now = Instant::now();
        self.last_seen
            .extend(servers.iter().map(|(id, _)| (*id, now)));
        self.last_seen
            .retain(|_, last_seen| now - *last_seen <= DISCONNECT_BEFORE);
    }
}

impl ServerMap {
    fn new(
        self_id: Option<Uuid>,
        init_servers: Vec<(Uuid, Server)>,
        update_send: UpdateSend,
    ) -> Self {
        let mut servers = HashBasedBiTable::with_capacity(init_servers.len());
        // Insert a sentinel value when we are a server.
        if let Some(self_id) = self_id {
            assert_matches!(servers.insert(self_id, None, None), Err((None, None)));
        }

        let this = Self {
            servers: Mutex::new(servers),
            tasks: JoinQueue::new(),
            update_send,
        };

        this.connect_many(init_servers);
        this
    }

    fn connect_many(&self, iter_servers: impl IntoIterator<Item = (Uuid, Server)>) {
        let mut servers = self.servers.must_lock();
        for (id, server) in iter_servers.into_iter() {
            self.connect_impl(&mut servers, id, server);
        }
    }

    fn connect(&self, id: Uuid, server: Server) {
        self.connect_impl(&mut self.servers.must_lock(), id, server);
    }

    fn connect_impl(&self, servers: &mut ServerTable, id: Uuid, server: Server) {
        match servers.get_row(&id) {
            Some((_, client)) => {
                if let Some(client) = client {
                    client.reconnect(server);
                }
            }
            None => {
                let (client, guard) = RawClient::connect(id, server);
                assert_matches!(
                    servers.insert(id, Some(guard.id()), Some(client)),
                    Err((None, None)),
                );
                self.tasks.push(guard).unwrap();
                let _ = self.update_send.send(Update::Start(id));
            }
        }
    }

    fn disconnect(&self, id: Uuid) {
        if let Some((_, Some(client))) = self.servers.must_lock().get_row(&id) {
            client.disconnect();
        }
    }

    fn handle_task(&self, mut guard: RawClientGuard) {
        let (id, client) = self
            .servers
            .must_lock()
            .remove_column(&Some(guard.id()))
            .unwrap();
        assert!(client.is_some());
        match guard.take_result() {
            Ok(Ok(())) => {}
            Ok(Err(error)) => tracing::warn!(%id, %error, "raw client error"),
            Err(error) => tracing::warn!(%id, %error, "raw client task error"),
        }
        let _ = self.update_send.send(Update::Stop(id));
    }

    fn all(&self) -> Result<Vec<(Uuid, Option<RawClient>)>, NotConnectedError> {
        let servers: Vec<_> = self
            .servers
            .must_lock()
            .iter()
            .map(|(id, _, client)| (*id, client.clone()))
            .collect();
        ensure!(!servers.is_empty(), NotConnectedSnafu);
        Ok(servers)
    }

    fn find(
        &self,
        key: &[u8],
        num_replicas: usize,
    ) -> Result<Vec<(Uuid, Option<RawClient>)>, NotConnectedError> {
        let mut servers = self
            .servers
            .must_lock()
            .iter()
            .map(|(id, _, client)| (*id, client.clone()))
            .collect_then_sort_by_key(service::rendezvous_sorting_by_key(key, |(id, _)| *id));
        ensure!(!servers.is_empty(), NotConnectedSnafu);
        servers.truncate(num_replicas);
        Ok(servers)
    }
}
