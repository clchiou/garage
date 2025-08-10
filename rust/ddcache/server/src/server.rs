use std::io::Error;
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
use tokio::time::{self, Instant};
use tracing::Instrument;

use g1_tokio::task::{Cancel, JoinGuard, JoinQueue};
use g1_zmq::Socket;
use g1_zmq::duplex::Duplex;
use g1_zmq::envelope::{Envelope, Frame, Multipart};

use ddcache_peer::Peer;
use ddcache_rpc::envelope;
use ddcache_rpc::{BlobEndpoint, Request, Timestamp, TimestampExt, Token};
use ddcache_storage::{ReadGuard, Storage, WriteGuard};

use crate::Guard;
use crate::rep;
use crate::state::State;

#[derive(Debug)]
pub(crate) struct Actor {
    cancel: Cancel,

    duplex: Duplex,
    max_key_size: usize,
    max_metadata_size: usize,
    max_blob_size: usize,

    tasks: JoinQueue<()>,
    concurrency: Arc<Semaphore>,

    blob_endpoints: Arc<[BlobEndpoint]>,

    state: Arc<State>,
    storage: Storage,
    storage_size_lwm: u64,
    storage_size_hwm: u64,

    peer: Peer,

    evict_task: Option<Guard>,
    expire_task: Option<Guard>,

    stats: Arc<Stats>,
}

#[derive(Debug)]
struct Handler {
    response_envelope: Envelope<()>,
    response_send: UnboundedSender<Envelope<Frame>>,

    blob_endpoints: Arc<[BlobEndpoint]>,

    state: Arc<State>,
    storage: Storage,

    peer: Peer,

    permit: Option<OwnedSemaphorePermit>,

    stats: Arc<Stats>,
}

#[derive(Debug, Default)]
struct Stats {
    read_hit: AtomicU64,
    read_miss: AtomicU64,
    write_lock_succeed: AtomicU64,
    write_lock_fail: AtomicU64,
}

impl Actor {
    pub(crate) fn spawn(
        socket: Socket,
        blob_endpoints: Vec<BlobEndpoint>,
        state: Arc<State>,
        storage: Storage,
        peer: Peer,
    ) -> Guard {
        Guard::spawn(move |cancel| {
            Self::new(
                cancel,
                socket.into(),
                blob_endpoints.into(),
                state,
                storage,
                peer,
            )
            .run()
        })
    }

    fn new(
        cancel: Cancel,
        duplex: Duplex,
        blob_endpoints: Arc<[BlobEndpoint]>,
        state: Arc<State>,
        storage: Storage,
        peer: Peer,
    ) -> Self {
        Self {
            cancel: cancel.clone(),

            duplex,
            max_key_size: *crate::max_key_size(),
            max_metadata_size: *crate::max_metadata_size(),
            max_blob_size: *crate::max_blob_size(),

            tasks: JoinQueue::with_cancel(cancel),
            concurrency: Arc::new(Semaphore::new(*crate::max_concurrency())),

            blob_endpoints,

            state,
            storage,
            storage_size_lwm: *crate::storage_size_lwm(),
            storage_size_hwm: *crate::storage_size_hwm(),

            peer,

            evict_task: None,
            expire_task: None,

            stats: Arc::new(Default::default()),
        }
    }

    async fn run(mut self) -> Result<(), Error> {
        let (response_send, mut response_recv) = mpsc::unbounded_channel();

        let mut deadline = None;
        tokio::pin! { let timeout = OptionFuture::from(None); }

        let mut log_stats_interval = time::interval(Duration::from_secs(600));

        loop {
            let next_deadline = self.state.next_deadline();
            if deadline != next_deadline {
                deadline = next_deadline;
                timeout.set(deadline.map(time::sleep_until).into());
            }

            tokio::select! {
                () = self.cancel.wait() => break,

                request = self.duplex.try_next() => {
                    let Some(request) = request? else { break };
                    self.handle_request(request, &response_send);
                }
                response = response_recv.recv() => {
                    let Some(response) = response else { break };
                    // Block the actor loop on `duplex.send` because it is probably desirable to
                    // derive back pressure from this point.
                    self.duplex.send(response.into()).await?;
                }

                Some(()) = &mut timeout => {
                    self.state.remove_expired(Instant::now());
                    deadline = None;
                    timeout.set(None.into());
                }

                guard = self.tasks.join_next() => {
                    let Some(guard) = guard else { break };
                    self.handle_task(guard);
                    // We check and spawn an evict task regardless of whether `guard` is write, and
                    // we do so even before the client completes writing to the blob.  While this
                    // may seem a bit unusual, it should not pose any issues in practice.
                    self.check_then_spawn_evict();
                }

                Some(()) = {
                    OptionFuture::from(self.evict_task.as_mut())
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
                    OptionFuture::from(self.expire_task.as_mut())
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
            (&mut guard).await;
            self.handle_cleanup_task(guard)?;
        }

        Ok(())
    }

    fn handle_request(&self, request: Multipart, response_send: &UnboundedSender<Envelope<Frame>>) {
        let envelope = match envelope::decode_request(request) {
            Ok(envelope) => envelope,
            Err(error) => {
                match error {
                    envelope::Error::InvalidFrameSequence { frames } => {
                        tracing::warn!(?frames, "invalid frame sequence");
                        // TODO: What else could we do?
                    }
                    envelope::Error::Decode { source, envelope } => {
                        tracing::warn!(?envelope, error = %source, "decode error");
                        let _ = response_send.send(envelope.map(|()| rep::invalid_request_error()));
                    }
                    envelope::Error::ExpectOneDataFrame { envelope } => {
                        tracing::warn!(?envelope, "expect exactly one data frame");
                        let _ = response_send.send(envelope.map(|_| rep::invalid_request_error()));
                    }
                }
                return;
            }
        };
        tracing::debug!(request = ?&**envelope.data());

        let request = match Request::try_from(**envelope.data()) {
            Ok(request) => request,
            Err(error) => {
                tracing::warn!(request = ?&**envelope.data(), %error, "decode error");
                let _ = response_send.send(envelope.map(|_| rep::invalid_request_error()));
                return;
            }
        };

        let Ok(permit) = self.concurrency.clone().try_acquire_owned() else {
            let _ = response_send.send(envelope.map(|_| rep::unavailable_error()));
            return;
        };
        let handler = Handler::new(self, envelope.map(|_| ()), response_send.clone(), permit);

        let max_key_size = self.max_key_size;
        let max_metadata_size = self.max_metadata_size;
        let max_blob_size = self.max_blob_size;

        macro_rules! check_key {
            ($key:ident $(,)?) => {
                if $key.len() > max_key_size {
                    tracing::warn!(key = %$key.escape_ascii(), max_key_size, "max size exceeded");
                    handler.send_response(rep::max_key_size_exceeded_error());
                    return;
                }
            };
        }

        macro_rules! check_metadata {
            ($metadata:expr $(,)?) => {{
                let metadata = $metadata;
                if metadata.len() > max_metadata_size {
                    tracing::warn!(
                        metadata = %metadata.escape_ascii(),
                        max_metadata_size,
                        "max size exceeded",
                    );
                    handler.send_response(rep::max_metadata_size_exceeded_error());
                    return;
                }
            }};
        }

        macro_rules! check_size {
            ($size:ident $(,)?) => {
                if $size > max_blob_size {
                    tracing::warn!($size, max_blob_size, "max size exceeded");
                    handler.send_response(rep::max_blob_size_exceeded_error());
                    return;
                }
            };
        }

        match request {
            Request::Cancel(token) => {
                let span = tracing::info_span!("ddcache/cancel");
                let _enter = span.enter();
                handler.cancel(token);
            }

            Request::Read { key } => {
                self.tasks
                    .push(JoinGuard::spawn(move |cancel| {
                        async move {
                            check_key!(key);
                            tokio::select! {
                                () = cancel.wait() => {}
                                () = handler.read(key) => {}
                            }
                        }
                        .instrument(tracing::info_span!("ddcache/read"))
                    }))
                    .unwrap();
            }

            Request::ReadMetadata { key } => {
                self.tasks
                    .push(JoinGuard::spawn(move |cancel| {
                        async move {
                            check_key!(key);
                            tokio::select! {
                                () = cancel.wait() => {}
                                () = handler.read_metadata(key) => {}
                            }
                        }
                        .instrument(tracing::info_span!("ddcache/read-metadata"))
                    }))
                    .unwrap();
            }

            Request::Write {
                key,
                metadata,
                size,
                expire_at,
            } => {
                let span = tracing::info_span!("ddcache/write");
                let _enter = span.enter();
                check_key!(key);
                check_metadata!(metadata.as_deref().unwrap_or(&[]));
                check_size!(size);
                handler.write(key, metadata, size, expire_at);
            }

            Request::WriteMetadata {
                key,
                metadata,
                expire_at,
            } => {
                let span = tracing::info_span!("ddcache/write-metadata");
                let _enter = span.enter();
                check_key!(key);
                check_metadata!(
                    metadata
                        .as_ref()
                        .map_or(&[] as &[u8], |x| x.as_deref().unwrap_or(&[]))
                );
                handler.write_metadata(key, metadata, expire_at);
            }

            Request::Remove { key } => {
                self.tasks
                    .push(JoinGuard::spawn(move |cancel| {
                        async move {
                            check_key!(key);
                            tokio::select! {
                                () = cancel.wait() => {}
                                () = handler.remove(key) => {}
                            }
                        }
                        .instrument(tracing::info_span!("ddcache/remove"))
                    }))
                    .unwrap();
            }

            Request::Pull { key } => {
                self.tasks
                    .push(JoinGuard::spawn(move |cancel| {
                        async move {
                            check_key!(key);
                            tokio::select! {
                                () = cancel.wait() => {}
                                () = handler.pull(key) => {}
                            }
                        }
                        .instrument(tracing::info_span!("ddcache/pull"))
                    }))
                    .unwrap();
            }

            Request::Push {
                key,
                metadata,
                size,
                expire_at,
            } => {
                let span = tracing::info_span!("ddcache/push");
                let _enter = span.enter();
                check_key!(key);
                check_metadata!(metadata.as_deref().unwrap_or(&[]));
                check_size!(size);
                handler.push(key, metadata, size, expire_at);
            }
        }
    }

    fn handle_task(&self, mut guard: JoinGuard<()>) {
        match guard.take_result() {
            Ok(()) => {}
            Err(error) => tracing::warn!(%error, "handler task error"),
        }
    }

    fn check_then_spawn_evict(&mut self) {
        if self.evict_task.is_none() && self.storage.size() > self.storage_size_hwm {
            self.evict_task = Some(Guard::spawn(|cancel| {
                evict(cancel, self.storage.clone(), self.storage_size_lwm)
                    .instrument(tracing::info_span!("ddcache/evict"))
            }));
        }
    }

    fn spawn_expire(&mut self) {
        assert!(self.expire_task.is_none());
        self.expire_task = Some(Guard::spawn(|cancel| {
            expire(cancel, self.storage.clone()).instrument(tracing::info_span!("ddcache/expire"))
        }));
    }

    fn handle_cleanup_task(&self, mut guard: Guard) -> Result<(), Error> {
        match guard.take_result() {
            Ok(result) => result,
            Err(error) => {
                tracing::warn!(%error, "cleanup task error");
                Ok(())
            }
        }
    }
}

impl Handler {
    fn new(
        server: &Actor,
        response_envelope: Envelope<()>,
        response_send: UnboundedSender<Envelope<Frame>>,
        permit: OwnedSemaphorePermit,
    ) -> Self {
        Self {
            response_envelope,
            response_send,

            blob_endpoints: server.blob_endpoints.clone(),

            state: server.state.clone(),
            storage: server.storage.clone(),

            peer: server.peer.clone(),

            permit: Some(permit),

            stats: server.stats.clone(),
        }
    }

    fn send_response(self, response: Frame) {
        let _ = self
            .response_send
            .send(self.response_envelope.map(|()| response));
    }
}

impl Handler {
    fn cancel(self, token: Token) {
        if self.state.remove(token).is_some() {
            tracing::debug!(token, "cancel");
        }
        self.send_response(rep::cancel_response());
    }
}

impl Handler {
    async fn read(mut self, key: Bytes) {
        // TODO: Pick a blob endpoint matching the client endpoint.
        let Some(endpoint) = self.blob_endpoints.first().copied() else {
            self.send_response(rep::ok_none_response());
            return;
        };

        let Some(reader) = self.read_lock(key.clone()).await else {
            self.peer.try_pull(key);
            self.send_response(rep::ok_none_response());
            return;
        };

        let metadata = reader.metadata();
        let size = reader.size();
        let expire_at = reader.expire_at();

        // No errors after this point.

        let permit = self.permit.take().unwrap();
        let token = self.state.insert_reader((reader, permit));
        tracing::debug!(token);
        self.send_response(rep::read_response(
            metadata,
            size.try_into().unwrap(),
            expire_at,
            endpoint,
            token,
        ));
    }

    async fn read_metadata(self, key: Bytes) {
        let Some(reader) = self.read_lock(key.clone()).await else {
            self.peer.try_pull(key);
            self.send_response(rep::ok_none_response());
            return;
        };

        self.send_response(rep::read_metadata_response(
            reader.metadata(),
            reader.size().try_into().unwrap(),
            reader.expire_at(),
        ));
    }

    async fn read_lock(&self, key: Bytes) -> Option<ReadGuard> {
        let reader = self.storage.read(key).await;
        match reader {
            Some(_) => self.stats.read_hit.fetch_add(1, Ordering::SeqCst),
            None => self.stats.read_miss.fetch_add(1, Ordering::SeqCst),
        };
        reader
    }
}

impl Handler {
    fn write(
        mut self,
        key: Bytes,
        metadata: Option<Bytes>,
        size: usize,
        expire_at: Option<Timestamp>,
    ) {
        // TODO: Pick a blob endpoint matching the client endpoint.
        let Some(endpoint) = self.blob_endpoints.first().copied() else {
            self.send_response(rep::ok_none_response());
            return;
        };

        let Some(mut writer) = self.try_write_lock(key, true) else {
            self.send_response(rep::ok_none_response());
            return;
        };

        writer.set_metadata(metadata);
        writer.set_expire_at(expire_at);

        // No errors after this point.

        let permit = self.permit.take().unwrap();
        let token = self.state.insert_writer((writer, size, permit));
        tracing::debug!(token);
        self.send_response(rep::write_response(endpoint, token));
    }

    fn write_metadata(
        self,
        key: Bytes,
        new_metadata: Option<Option<Bytes>>,
        new_expire_at: Option<Option<Timestamp>>,
    ) {
        let Some(mut writer) = self.try_write_lock(key.clone(), false) else {
            self.send_response(rep::ok_none_response());
            return;
        };

        // Do NOT create an empty file.  If creating an empty file is indeed your intention, please
        // pass 0 as `size` to `write`.
        if writer.is_new() {
            self.send_response(rep::ok_none_response());
            return;
        }

        let metadata = writer.metadata();
        let size = writer.size();
        let expire_at = writer.expire_at();

        if let Some(new_metadata) = new_metadata {
            writer.set_metadata(new_metadata);
        }
        if let Some(new_expire_at) = new_expire_at {
            writer.set_expire_at(new_expire_at);
        }

        self.send_response(match writer.commit() {
            Ok(()) => rep::write_metadata_response(metadata, size.try_into().unwrap(), expire_at),
            Err(error) => {
                tracing::warn!(key = %key.escape_ascii(), %error, "writer commit error");
                rep::server_error()
            }
        });
    }

    // TODO: Call `try_write` here because I believe that, as a cache, it is not very critical to
    // always update an entry.  Perhaps we should expose the interface to the client to force an
    // update?
    fn try_write_lock(&self, key: Bytes, truncate: bool) -> Option<WriteGuard> {
        let writer = self.storage.try_write(key, truncate);
        match writer {
            Some(_) => self.stats.write_lock_succeed.fetch_add(1, Ordering::SeqCst),
            None => self.stats.write_lock_fail.fetch_add(1, Ordering::SeqCst),
        };
        writer
    }
}

impl Handler {
    async fn remove(self, key: Bytes) {
        let response = match self.storage.remove(key.clone()).await {
            Ok(Some((metadata, size, expire_at))) => {
                rep::remove_response(metadata, size.try_into().unwrap(), expire_at)
            }
            Ok(None) => rep::ok_none_response(),
            Err(error) => {
                tracing::warn!(key = %key.escape_ascii(), %error, "remove error");
                rep::server_error()
            }
        };
        self.send_response(response);
    }
}

impl Handler {
    async fn pull(mut self, key: Bytes) {
        // TODO: Pick a blob endpoint matching the peer endpoint.
        let Some(endpoint) = self.blob_endpoints.first().copied() else {
            self.send_response(rep::ok_none_response());
            return;
        };

        // Do not update the blob's recency.
        let Some(reader) = self.storage.peek(key).await else {
            self.send_response(rep::ok_none_response());
            return;
        };

        let metadata = reader.metadata();
        let size = reader.size();
        let expire_at = reader.expire_at();

        // No errors after this point.

        let permit = self.permit.take().unwrap();
        let token = self.state.insert_reader((reader, permit));
        tracing::debug!(token);
        self.send_response(rep::pull_response(
            metadata,
            size.try_into().unwrap(),
            expire_at,
            endpoint,
            token,
        ));
    }

    fn push(
        mut self,
        key: Bytes,
        metadata: Option<Bytes>,
        size: usize,
        expire_at: Option<Timestamp>,
    ) {
        // TODO: Pick a blob endpoint matching the peer endpoint.
        let Some(endpoint) = self.blob_endpoints.first().copied() else {
            self.send_response(rep::ok_none_response());
            return;
        };

        // Decline the push request if we have the blob.
        let Some(mut writer) = self.storage.write_new(key) else {
            self.send_response(rep::ok_none_response());
            return;
        };

        writer.set_metadata(metadata);
        writer.set_expire_at(expire_at);

        // No errors after this point.

        let permit = self.permit.take().unwrap();
        let token = self.state.insert_writer((writer, size, permit));
        tracing::debug!(token);
        self.send_response(rep::push_response(endpoint, token));
    }
}

async fn evict(cancel: Cancel, storage: Storage, target_size: u64) -> Result<(), Error> {
    let old_size = storage.size();
    let start = Instant::now();
    let new_size = tokio::select! {
        () = cancel.wait() => return Ok(()),
        size = storage.evict(target_size) => size?,
    };
    let duration = start.elapsed();
    tracing::info!(old_size, new_size, ?duration, "evict");
    Ok(())
}

async fn expire(cancel: Cancel, storage: Storage) -> Result<(), Error> {
    let old_size = storage.size();
    let start = Instant::now();
    tokio::select! {
        () = cancel.wait() => return Ok(()),
        result = storage.expire(Timestamp::now()) => result?,
    }
    let duration = start.elapsed();
    let new_size = storage.size();
    tracing::info!(old_size, new_size, ?duration, "expire");
    Ok(())
}
