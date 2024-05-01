use std::cmp;
use std::fs::File;
use std::io;
use std::os::fd::{AsFd, AsRawFd, BorrowedFd};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex, MutexGuard,
};

use bytes::Bytes;
use futures::future::OptionFuture;
use futures::stream::StreamExt;
use tokio::sync::{mpsc, oneshot, watch};
use uuid::Uuid;

use etcd_pubsub::SubscriberError;
use g1_base::future::ReadyQueue;
use g1_base::sync::MutexExt;
use g1_tokio::task::{Cancel, JoinGuard, JoinQueue};

use ddcache_rpc::service::{self, Event, Subscriber};
use ddcache_rpc::{Endpoint, Token};

use crate::error::Error;
use crate::route::RouteMap;
use crate::shard::{Shard, ShardGuard};

type Connect = (Endpoint, oneshot::Sender<Result<(), Error>>);
type ConnectRecv = mpsc::Receiver<Connect>;
type ConnectSend = mpsc::Sender<Connect>;

#[derive(Clone, Debug)]
pub struct Client {
    service_ready_recv: watch::Receiver<Option<bool>>,
    connect_send: ConnectSend,
    routes: Arc<Mutex<RouteMap>>,
    num_replicas: usize,
}

pub type ClientGuard = JoinGuard<Result<(), io::Error>>;

#[derive(Clone, Debug)]
pub struct BlobInfo {
    pub metadata: Option<Bytes>,
    pub size: usize,
}

#[derive(Debug)]
struct Actor {
    cancel: Cancel,
    service_ready_send: watch::Sender<Option<bool>>,
    connect_recv: ConnectRecv,
    routes: Arc<Mutex<RouteMap>>,
    tasks: JoinQueue<Result<(), io::Error>>,
}

// le = last error

macro_rules! le_push {
    ($message:tt, $last_error:ident, $endpoint:expr, $error:expr) => {
        if let Some((endpoint, error)) = $last_error.replace(($endpoint, $error)) {
            tracing::warn!(%endpoint, %error, $message);
        }
    };
}

macro_rules! le_finish {
    ($message:tt, $last_error:ident, $succeed:expr) => {
        if let Some((endpoint, error)) = $last_error {
            if $succeed {
                tracing::warn!(%endpoint, %error, $message);
            } else {
                return Err(error);
            }
        }
    };
}

impl Client {
    pub fn spawn() -> (Self, ClientGuard) {
        let (service_ready_send, service_ready_recv) = watch::channel(None);
        let (connect_send, connect_recv) = mpsc::channel(16);
        let routes = Arc::new(Mutex::new(RouteMap::new()));
        (
            Self {
                service_ready_recv,
                connect_send,
                routes: routes.clone(),
                num_replicas: *crate::num_replicas(),
            },
            ClientGuard::spawn(move |cancel| {
                Actor::new(cancel, service_ready_send, connect_recv, routes).run()
            }),
        )
    }

    pub async fn service_ready(&mut self) -> bool {
        self.service_ready_recv
            .wait_for(|x| x.is_some())
            .await
            .map_or(false, |x| (*x).unwrap())
    }

    pub async fn connect(&self, endpoint: Endpoint) -> Result<(), Error> {
        let (result_send, result_recv) = oneshot::channel();
        self.connect_send
            .send((endpoint, result_send))
            .await
            .map_err(|_| Error::Stopped)?;
        result_recv.await.map_err(|_| Error::Stopped)?
    }

    pub fn disconnect(&self, endpoint: Endpoint) {
        self.routes.must_lock().disconnect(endpoint);
    }

    fn get(&self, endpoint: Endpoint) -> Result<Shard, Error> {
        self.routes.must_lock().get(endpoint)
    }

    fn find(&self, key: &[u8]) -> Result<Vec<Shard>, Error> {
        self.routes.must_lock().find(key, self.num_replicas)
    }

    //
    // TODO: Should we disconnect from (or reconnect to) the shard on error?
    //

    pub async fn ping(&self, endpoint: Endpoint) -> Result<(), Error> {
        self.get(endpoint)?.ping().await
    }

    pub async fn read<F>(
        &self,
        key: Bytes,
        output: &mut F,
        size: Option<usize>,
    ) -> Result<Option<BlobInfo>, Error>
    where
        F: AsFd + Send,
    {
        let queue = ReadyQueue::new();
        let first = Arc::new(AtomicBool::new(true));
        for shard in self.find(&key)? {
            let key = key.clone();
            let first = first.clone();
            assert!(queue
                .push(async move {
                    let response = shard.read(&key).await;
                    if !matches!(response, Ok(Some(_))) || first.swap(false, Ordering::SeqCst) {
                        return (shard, response);
                    }

                    let response = shard
                        .cancel(response.unwrap().unwrap().blob.unwrap().token())
                        .await
                        .map(|()| None);
                    (shard, response)
                })
                .is_ok());
        }
        queue.close();

        let mut succeed = false;
        let mut last_error = None;
        let mut metadata = None;

        while let Some((shard, response)) = queue.pop_ready().await {
            let response = match response {
                Ok(Some(response)) => response,
                Ok(None) => continue,
                Err(error) => {
                    le_push!("read", last_error, shard.endpoint(), error);
                    continue;
                }
            };

            let size = cmp::min(response.size, size.unwrap_or(usize::MAX));
            metadata = Some(BlobInfo {
                metadata: response.metadata,
                size,
            });

            match response.blob.unwrap().read(output, size).await {
                Ok(()) => succeed = true,
                Err(error) => le_push!("read", last_error, shard.endpoint(), error),
            }

            join_cancels(queue);
            break;
        }

        le_finish!("read", last_error, succeed);
        Ok(metadata)
    }

    pub async fn read_metadata(&self, key: Bytes) -> Result<Option<BlobInfo>, Error> {
        let queue = ReadyQueue::new();
        for shard in self.find(&key)? {
            let key = key.clone();
            assert!(queue
                .push(async move {
                    let response = shard.read_metadata(&key).await;
                    (shard, response)
                })
                .is_ok());
        }
        queue.close();

        let mut metadata = None;
        let mut last_error = None;

        while let Some((shard, response)) = queue.pop_ready().await {
            let response = match response {
                Ok(Some(response)) => response,
                Ok(None) => continue,
                Err(error) => {
                    le_push!("read_metadata", last_error, shard.endpoint(), error);
                    continue;
                }
            };

            metadata = Some(BlobInfo {
                metadata: response.metadata,
                size: response.size,
            });

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
    ) -> Result<bool, Error>
    where
        F: AsFd + Send,
    {
        let queue = ReadyQueue::new();
        let first = Arc::new(AtomicBool::new(true));
        for shard in self.find(&key)? {
            let key = key.clone();
            let metadata = metadata.clone();
            let first = first.clone();
            assert!(queue
                .push(async move {
                    let response = shard.write(&key, metadata.as_deref(), size).await;
                    if !matches!(response, Ok(Some(_))) || first.swap(false, Ordering::SeqCst) {
                        return (shard, response);
                    }

                    let response = shard
                        .cancel(response.unwrap().unwrap().blob.unwrap().token())
                        .await
                        .map(|()| None);
                    (shard, response)
                })
                .is_ok());
        }
        queue.close();

        let mut succeed = false;
        let mut last_error = None;

        while let Some((shard, response)) = queue.pop_ready().await {
            let response = match response {
                Ok(Some(response)) => response,
                Ok(None) => continue,
                Err(error) => {
                    le_push!("write_any", last_error, shard.endpoint(), error);
                    continue;
                }
            };

            match response.blob.unwrap().write(input, size).await {
                Ok(()) => succeed = true,
                Err(error) => le_push!("write_any", last_error, shard.endpoint(), error),
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
    ) -> Result<bool, Error> {
        let queue = ReadyQueue::new();
        let fd = input.as_raw_fd();
        for shard in self.find(&key)? {
            let key = key.clone();
            let metadata = metadata.clone();
            assert!(queue
                .push(async move {
                    let response = match shard.write(&key, metadata.as_deref(), size).await {
                        Ok(Some(response)) => response,
                        Ok(None) => return (shard, Ok(false)),
                        Err(error) => return (shard, Err(error)),
                    };

                    let mut input = unsafe { BorrowedFd::borrow_raw(fd) };
                    match response
                        .blob
                        .unwrap()
                        .write_file(&mut input, Some(0), size)
                        .await
                    {
                        Ok(()) => (shard, Ok(true)),
                        Err(error) => (shard, Err(error)),
                    }
                })
                .is_ok());
        }
        queue.close();

        let mut succeed = false;
        let mut last_error = None;

        while let Some((shard, response)) = queue.pop_ready().await {
            match response {
                Ok(true) => succeed = true,
                Ok(false) => {}
                Err(error) => le_push!("write_all", last_error, shard.endpoint(), error),
            }
        }

        le_finish!("write_all", last_error, succeed);
        Ok(succeed)
    }

    pub async fn cancel(&self, endpoint: Endpoint, token: Token) -> Result<(), Error> {
        self.get(endpoint)?.cancel(token).await
    }
}

fn join_cancels<T>(queue: ReadyQueue<(Shard, Result<Option<T>, Error>)>)
where
    T: Send + 'static,
{
    // Do not block on joining the `shard.cancel()` futures.
    tokio::spawn(async move {
        while let Some((shard, response)) = queue.pop_ready().await {
            match response {
                Ok(Some(_)) => std::panic!("expect Ok(None) or Err"),
                Ok(None) => {}
                Err(error) => tracing::debug!(endpoint = %shard.endpoint(), %error, "cancel"),
            }
        }
    });
}

impl Actor {
    fn new(
        cancel: Cancel,
        service_ready_send: watch::Sender<Option<bool>>,
        connect_recv: ConnectRecv,
        routes: Arc<Mutex<RouteMap>>,
    ) -> Self {
        Self {
            cancel,
            service_ready_send,
            connect_recv,
            routes,
            tasks: JoinQueue::new(),
        }
    }

    fn connect(&self, endpoint: Endpoint) -> Result<(), Error> {
        self.routes.must_lock().connect(&self.tasks, endpoint)
    }

    fn connect_many(&self, routes: &mut MutexGuard<RouteMap>, id: Uuid, endpoints: Vec<String>) {
        for endpoint in endpoints.into_iter().map(Endpoint::from) {
            if let Err(error) = routes.connect(&self.tasks, endpoint.clone()) {
                tracing::warn!(%id, %endpoint, %error, "connect");
            }
        }
    }

    async fn run(mut self) -> Result<(), io::Error> {
        let mut subscriber = self
            .init_subscriber()
            .await
            .inspect_err(|error| {
                // Log it at the error level because we expect that `Client` will need a subscriber
                // in most use cases.
                tracing::error!(%error, "init subscriber");
            })
            .ok();
        let _ = self
            .service_ready_send
            .send_replace(Some(subscriber.is_some()));

        loop {
            tokio::select! {
                () = self.cancel.wait() => break,

                Some(event) = OptionFuture::from(subscriber.as_mut().map(|s| s.next())) => {
                    match event {
                        Some(Ok(event)) => self.handle_subscribe(event),
                        Some(Err(error)) => tracing::warn!(%error, "subscriber event"),
                        None => {
                            tracing::warn!("subscriber stop unexpectedly");
                            break;
                        }
                    }
                }

                connect = self.connect_recv.recv() => {
                    let Some(connect) = connect else { break };
                    self.handle_connect(connect);
                }

                guard = self.tasks.join_next() => {
                    let Some(guard) = guard else { break };
                    self.handle_task(guard, true)?;
                }
            }
        }

        self.tasks.cancel();
        while let Some(guard) = self.tasks.join_next().await {
            self.handle_task(guard, false)?;
        }

        Ok(())
    }

    async fn init_subscriber(&self) -> Result<Subscriber, SubscriberError> {
        let pubsub = service::pubsub();

        let subscriber = pubsub.subscribe().await?;

        let services = pubsub.scan().await?;
        {
            let mut routes = self.routes.must_lock();
            for (id, service) in services {
                tracing::info!(%id, ?service, "init");
                self.connect_many(&mut routes, id, service.endpoints);
            }
        }

        Ok(subscriber)
    }

    fn handle_subscribe(&self, event: Event) {
        let mut routes = self.routes.must_lock();
        match event {
            Event::Create((id, service)) => {
                tracing::info!(%id, ?service, "new service");
                self.connect_many(&mut routes, id, service.endpoints);
            }
            Event::Update { id, new, old } => {
                tracing::info!(%id, ?new, ?old, "update service");
                for endpoint in old.endpoints {
                    if !new.endpoints.contains(&endpoint) {
                        routes.disconnect(endpoint.into());
                    }
                }
                self.connect_many(&mut routes, id, new.endpoints);
            }
            Event::Delete((id, service)) => {
                tracing::info!(%id, ?service, "remove service");
                for endpoint in service.endpoints {
                    routes.disconnect(endpoint.into());
                }
            }
        }
    }

    fn handle_connect(&self, (endpoint, result_send): Connect) {
        let _ = result_send.send(self.connect(endpoint));
    }

    fn handle_task(
        &self,
        mut guard: ShardGuard,
        reconnect_on_error: bool,
    ) -> Result<(), io::Error> {
        let mut routes = self.routes.must_lock();
        let shard = routes.remove(guard.id()).unwrap();

        match guard.take_result() {
            Ok(Ok(())) => return Ok(()),
            Ok(Err(error)) => {
                if reconnect_on_error {
                    tracing::warn!(%error, "shard error");
                } else {
                    return Err(error);
                }
            }
            Err(error) => {
                if reconnect_on_error {
                    tracing::warn!(%error, "shard task error");
                } else {
                    return Err(error.into());
                }
            }
        }
        assert!(reconnect_on_error);

        routes
            .connect(&self.tasks, shard.endpoint())
            .map_err(|error| match error {
                Error::Connect { source } => source,
                _ => std::unreachable!("expect Error::Connect: {}", error),
            })
    }
}
