use std::io;
use std::sync::{
    Arc,
    atomic::{AtomicU64, Ordering},
};
use std::time::Duration;

use bytes::Bytes;
use futures::future::OptionFuture;
use futures::sink::SinkExt;
use futures::stream::TryStreamExt;
use tokio::sync::mpsc::{self, UnboundedSender};
use tokio::sync::{OwnedSemaphorePermit, Semaphore};
use tokio::task;
use tokio::time::{self, Instant};
use tracing::Instrument;

use g1_tokio::task::{Cancel, JoinGuard, JoinQueue};
use g1_zmq::Socket;
use g1_zmq::duplex::Duplex;
use g1_zmq::envelope::{Envelope, Frame, Multipart};

use dkvcache_peer::Peer;
use dkvcache_rpc::envelope;
use dkvcache_rpc::{
    Error, Request, Response, ResponseResult, ResponseResultExt, Timestamp, TimestampExt,
};
use dkvcache_storage::{Entry, Storage};

use crate::Guard;

//
// TODO: Should we wrap or not wrap storage calls in `task::spawn_blocking`?
//

#[derive(Debug)]
pub(crate) struct Actor {
    cancel: Cancel,

    duplex: Duplex,
    max_key_size: usize,
    max_value_size: usize,

    tasks: JoinQueue<()>,
    concurrency: Arc<Semaphore>,

    storage: Storage,
    storage_len_lwm: usize,
    storage_len_hwm: usize,

    peer: Peer,

    evict_task: Option<Guard>,
    expire_task: Option<Guard>,

    stats: Arc<Stats>,
}

#[derive(Debug)]
struct HandlerSpawner<'a> {
    server: &'a Actor,
    envelope: Envelope<Frame>,
    response_send: &'a ResponseSend,
}

#[derive(Debug)]
struct Handler {
    envelope: Envelope<Frame>,
    response_send: ResponseSend,

    storage: Storage,

    peer: Peer,

    _permit: OwnedSemaphorePermit,

    stats: Arc<Stats>,
}

type ResponseSend = UnboundedSender<Envelope<ResponseResult>>;

#[derive(Debug, Default)]
struct Stats {
    get_hit: AtomicU64,
    get_miss: AtomicU64,
}

impl Actor {
    pub(crate) fn spawn(socket: Socket, storage: Storage, peer: Peer) -> Guard {
        Guard::spawn(move |cancel| Self::new(cancel, socket.into(), storage, peer).run())
    }

    fn new(cancel: Cancel, duplex: Duplex, storage: Storage, peer: Peer) -> Self {
        Self {
            cancel: cancel.clone(),

            duplex,
            max_key_size: *crate::max_key_size(),
            max_value_size: *crate::max_value_size(),

            tasks: JoinQueue::with_cancel(cancel),
            concurrency: Arc::new(Semaphore::new(*crate::max_concurrency())),

            storage,
            storage_len_lwm: *crate::storage_len_lwm(),
            storage_len_hwm: *crate::storage_len_hwm(),

            peer,

            evict_task: None,
            expire_task: None,

            stats: Arc::new(Default::default()),
        }
    }

    async fn run(mut self) -> Result<(), io::Error> {
        let (response_send, mut response_recv) = mpsc::unbounded_channel();

        let mut log_stats_interval = time::interval(Duration::from_secs(600));

        loop {
            tokio::select! {
                () = self.cancel.wait() => break,

                request = self.duplex.try_next() => {
                    let Some(request) = request? else { break };
                    self.handle_request(request, &response_send);
                }
                response = response_recv.recv() => {
                    let Some(response) = response else { break };
                    let response = response.map(|response| Frame::from(ResponseResult::encode(response)));
                    // Block the actor loop on `duplex.send` because it is probably desirable to
                    // derive back pressure from this point.
                    self.duplex.send(response.into()).await?;
                }

                guard = self.tasks.join_next() => {
                    let Some(guard) = guard else { break };
                    self.handle_task(guard);
                    // We check and spawn an evict task regardless of whether `guard` is setting an
                    // entry.  While this may seem a bit unusual, it should not pose any issues in
                    // practice.
                    self.check_then_spawn_evict();
                }

                Some(()) = {
                    OptionFuture::from(self.evict_task.as_mut().map(|guard| guard.join()))
                } => {
                    let guard = self.evict_task.take().unwrap();
                    self.handle_cleanup_task(guard)?;
                }

                Some(()) = {
                    OptionFuture::from(
                        if self.expire_task.is_none() {
                            self.storage.next_expire_at()
                        } else {
                            None
                        }
                        .map(|t| (t - Timestamp::now()).to_std().unwrap_or_default())
                        .map(time::sleep),
                    )
                } => {
                    self.spawn_expire();
                }
                Some(()) = {
                    OptionFuture::from(self.expire_task.as_mut().map(|guard| guard.join()))
                } => {
                    let guard = self.expire_task.take().unwrap();
                    self.handle_cleanup_task(guard)?;
                }

                _ = log_stats_interval.tick() => tracing::info!(stats = ?self.stats),
            }
        }
        tracing::info!(stats = ?self.stats);

        self.tasks.cancel();
        while let Some(guard) = self.tasks.join_next().await {
            self.handle_task(guard);
        }

        for mut guard in self
            .evict_task
            .take()
            .into_iter()
            .chain(self.expire_task.take().into_iter())
        {
            guard.cancel();
            guard.join().await;
            self.handle_cleanup_task(guard)?;
        }

        Ok(())
    }

    fn handle_request(&self, request: Multipart, response_send: &ResponseSend) {
        let envelope = match envelope::decode(request) {
            Ok(envelope) => envelope,
            Err(error) => {
                tracing::warn!(%error, "envelope");
                match error {
                    envelope::Error::ExpectOneDataFrame { envelope } => {
                        let _ = response_send.send(envelope.map(|_| Err(Error::InvalidRequest)));
                    }
                    // TODO: What else could we do in this case?
                    envelope::Error::InvalidFrameSequence { .. } => {}
                }
                return;
            }
        };
        HandlerSpawner {
            server: self,
            envelope,
            response_send,
        }
        .spawn()
    }

    fn handle_task(&self, mut guard: JoinGuard<()>) {
        match guard.take_result() {
            Ok(()) => {}
            Err(error) => tracing::warn!(%error, "handler task error"),
        }
    }

    fn check_then_spawn_evict(&mut self) {
        if self.evict_task.is_none() && self.storage.len() > self.storage_len_hwm {
            self.evict_task = Some(Guard::spawn(|cancel| {
                evict(cancel, self.storage.clone(), self.storage_len_lwm)
                    .instrument(tracing::info_span!("dkvcache/evict"))
            }));
        }
    }

    fn spawn_expire(&mut self) {
        assert!(self.expire_task.is_none());
        self.expire_task = Some(Guard::spawn(|cancel| {
            expire(cancel, self.storage.clone()).instrument(tracing::info_span!("dkvcache/expire"))
        }));
    }

    fn handle_cleanup_task(&self, mut guard: Guard) -> Result<(), io::Error> {
        match guard.take_result() {
            Ok(result) => result,
            Err(error) => {
                tracing::warn!(%error, "cleanup task error");
                Ok(())
            }
        }
    }
}

impl<'a> HandlerSpawner<'a> {
    fn spawn(self) {
        macro_rules! spawn {
            ($name:expr, $method:ident ( $($arg:ident),* $(,)? ) $(,)?) => {{
                let permit = self.try_acquire()?;
                let (server, handler) = self.into_handler(permit);
                server
                    .tasks
                    .push(JoinGuard::spawn(move |cancel| {
                        async move {
                            tokio::select! {
                                () = cancel.wait() => {}
                                () = handler.$method($($arg),*) => {}
                            }
                        }
                        .instrument(tracing::info_span!($name))
                    }))
                    .unwrap();
                return;
            }};
        }

        let Err(response) = try {
            let request = Request::try_from(&**self.envelope.data())
                .inspect_err(|error| tracing::warn!(envelope = ?self.envelope, %error, "decode"))
                .map_err(|_| Err(Error::InvalidRequest))?;
            tracing::debug!(?request);

            match request {
                Request::Ping => return self.send_response(Ok(None)),

                Request::Get { key } => {
                    self.check_key(&key)?;
                    spawn!("dkvcache/get", get(key));
                }

                Request::Set {
                    key,
                    value,
                    expire_at,
                } => {
                    self.check_key(&key)?;
                    self.check_value(&value)?;
                    spawn!("dkvcache/set", set(key, value, expire_at));
                }

                Request::Update {
                    key,
                    value,
                    expire_at,
                } => {
                    self.check_key(&key)?;
                    if let Some(value) = value.as_ref() {
                        self.check_value(value)?;
                    }
                    spawn!("dkvcache/update", update(key, value, expire_at));
                }

                Request::Remove { key } => {
                    self.check_key(&key)?;
                    spawn!("dkvcache/remove", remove(key));
                }

                Request::Pull { key } => {
                    self.check_key(&key)?;
                    spawn!("dkvcache/pull", pull(key));
                }

                Request::Push {
                    key,
                    value,
                    expire_at,
                } => {
                    self.check_key(&key)?;
                    self.check_value(&value)?;
                    spawn!("dkvcache/push", push(key, value, expire_at));
                }
            }
        };
        self.send_response(response);
    }

    fn send_response(self, response: ResponseResult) {
        let _ = self.response_send.send(self.envelope.map(|_| response));
    }

    fn into_handler(self, permit: OwnedSemaphorePermit) -> (&'a Actor, Handler) {
        (
            self.server,
            Handler::new(
                self.server,
                self.envelope,
                self.response_send.clone(),
                permit,
            ),
        )
    }

    fn check_key(&self, key: &[u8]) -> Result<(), ResponseResult> {
        if key.len() <= self.server.max_key_size {
            Ok(())
        } else {
            tracing::warn!(
                key = %key.escape_ascii(),
                max_key_size = self.server.max_key_size,
                "max size exceeded",
            );
            Err(Err(Error::MaxKeySizeExceeded {
                max: self.server.max_key_size.try_into().unwrap(),
            }))
        }
    }

    fn check_value(&self, value: &[u8]) -> Result<(), ResponseResult> {
        if value.len() <= self.server.max_value_size {
            Ok(())
        } else {
            tracing::warn!(
                value = %value.escape_ascii(),
                max_value_size = self.server.max_value_size,
                "max size exceeded",
            );
            Err(Err(Error::MaxValueSizeExceeded {
                max: self.server.max_value_size.try_into().unwrap(),
            }))
        }
    }

    fn try_acquire(&self) -> Result<OwnedSemaphorePermit, ResponseResult> {
        self.server
            .concurrency
            .clone()
            .try_acquire_owned()
            .map_err(|_| Err(Error::Unavailable))
    }
}

impl Handler {
    fn new(
        server: &Actor,
        envelope: Envelope<Frame>,
        response_send: ResponseSend,
        permit: OwnedSemaphorePermit,
    ) -> Self {
        Self {
            envelope,
            response_send,

            storage: server.storage.clone(),

            peer: server.peer.clone(),

            _permit: permit,

            stats: server.stats.clone(),
        }
    }

    fn send_response(self, response: ResponseResult) {
        let _ = self.response_send.send(self.envelope.map(|_| response));
    }

    async fn get(self, key: Bytes) {
        let response = to_response(self.storage.get(&key));
        match response {
            Ok(Some(_)) => {
                self.stats.get_hit.fetch_add(1, Ordering::SeqCst);
            }
            Ok(None) => {
                self.stats.get_miss.fetch_add(1, Ordering::SeqCst);
                self.peer.try_pull(key);
            }
            Err(_) => {}
        }
        self.send_response(response)
    }

    async fn set(self, key: Bytes, value: Bytes, expire_at: Option<Timestamp>) {
        task::spawn_blocking(move || {
            let response = to_response(self.storage.set(&key, &value, expire_at));
            self.send_response(response)
        })
        .await
        .unwrap()
    }

    async fn update(self, key: Bytes, value: Option<Bytes>, expire_at: Option<Option<Timestamp>>) {
        task::spawn_blocking(move || {
            let response = to_response(self.storage.update(&key, value.as_deref(), expire_at));
            self.send_response(response)
        })
        .await
        .unwrap()
    }

    async fn remove(self, key: Bytes) {
        task::spawn_blocking(move || {
            let response = to_response(self.storage.remove(&key));
            self.send_response(response)
        })
        .await
        .unwrap()
    }

    async fn pull(self, key: Bytes) {
        let response = to_response(self.storage.peek(&key));
        self.send_response(response)
    }

    async fn push(self, key: Bytes, value: Bytes, expire_at: Option<Timestamp>) {
        task::spawn_blocking(move || {
            let response = to_response(self.storage.create(&key, &value, expire_at));
            self.send_response(response)
        })
        .await
        .unwrap()
    }
}

fn to_response(result: Result<Option<Entry>, dkvcache_storage::Error>) -> ResponseResult {
    match result {
        Ok(Some(entry)) => Ok(Some(Response {
            value: entry.value,
            expire_at: entry.expire_at,
        })),
        Ok(None) => Ok(None),
        Err(error) => {
            tracing::warn!(%error, "storage");
            Err(Error::Server)
        }
    }
}

async fn evict(cancel: Cancel, storage: Storage, target_len: usize) -> Result<(), io::Error> {
    let old_len = storage.len();
    let start = Instant::now();
    let new_len = tokio::select! {
        () = cancel.wait() => return Ok(()),
        len = {
            task::spawn_blocking(move || { storage.evict(target_len) })
        } => len.unwrap().map_err(io::Error::other)?,
    };
    let duration = start.elapsed();
    tracing::info!(old_len, new_len, ?duration, "evict");
    Ok(())
}

async fn expire(cancel: Cancel, storage: Storage) -> Result<(), io::Error> {
    let old_len = storage.len();
    let start = Instant::now();
    tokio::select! {
        () = cancel.wait() => return Ok(()),
        result = {
            let storage = storage.clone();
            task::spawn_blocking(move || { storage.expire(Timestamp::now()) })
        } => result.unwrap().map_err(io::Error::other)?,
    }
    let duration = start.elapsed();
    let new_len = storage.len();
    tracing::info!(old_len, new_len, ?duration, "expire");
    Ok(())
}
