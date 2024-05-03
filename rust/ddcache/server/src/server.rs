use std::fmt;
use std::io::Error;
use std::path::Path;
use std::sync::{
    atomic::{AtomicU64, Ordering},
    Arc,
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
use zmq::{Context, ROUTER};

use g1_capnp::owner::Owner;
use g1_tokio::task::{Cancel, JoinQueue};
use g1_zmq::duplex::Duplex;
use g1_zmq::envelope::{Envelope, Frame, Multipart};
use g1_zmq::Socket;

use ddcache_rpc::envelope;
use ddcache_rpc::rpc_capnp::request;
use ddcache_rpc::{BlobEndpoint, Endpoint};
use ddcache_storage::Storage;

use crate::rep;
use crate::state::State;
use crate::Guard;

#[derive(Debug)]
pub(crate) struct Actor {
    cancel: Cancel,

    duplex: Duplex,
    max_key_size: usize,
    max_metadata_size: usize,
    max_blob_size: usize,

    tasks: JoinQueue<Result<(), Error>>,
    concurrency: Arc<Semaphore>,

    blob_endpoints: Arc<[BlobEndpoint]>,

    state: Arc<State>,
    storage: Storage,
    storage_size_lwm: u64,
    storage_size_hwm: u64,

    stats: Arc<Stats>,
}

#[derive(Debug)]
struct Handler<R> {
    request: Option<Envelope<Owner<Frame, R>>>,
    response_send: UnboundedSender<Envelope<Frame>>,
    max_key_size: usize,
    max_metadata_size: usize,
    max_blob_size: usize,

    blob_endpoints: Arc<[BlobEndpoint]>,

    state: Arc<State>,
    storage: Storage,

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
    pub(crate) async fn spawn(
        storage_dir: &Path,
        blob_endpoints: Vec<BlobEndpoint>,
        state: Arc<State>,
    ) -> Result<(Vec<Endpoint>, Guard), Error> {
        let storage = Storage::open(storage_dir).await?;

        let socket = Socket::try_from(Context::new().socket(ROUTER)?)?;
        socket.set_linger(0)?; // Do NOT block the program exit!
        let mut endpoints = Vec::with_capacity(crate::endpoints().len());
        for endpoint in crate::endpoints() {
            socket.bind(endpoint)?;
            endpoints.push(socket.get_last_endpoint().unwrap().unwrap().into());
        }
        tracing::info!(?endpoints, "bind");

        Ok((
            endpoints,
            Guard::spawn(move |cancel| {
                Self::new(cancel, socket.into(), blob_endpoints.into(), state, storage).run()
            }),
        ))
    }

    fn new(
        cancel: Cancel,
        duplex: Duplex,
        blob_endpoints: Arc<[BlobEndpoint]>,
        state: Arc<State>,
        storage: Storage,
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

            stats: Arc::new(Default::default()),
        }
    }

    async fn run(mut self) -> Result<(), Error> {
        let (response_send, mut response_recv) = mpsc::unbounded_channel();

        let mut deadline = None;
        tokio::pin! { let timeout = OptionFuture::from(None); }

        let mut evict_task: Option<Guard> = None;

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
                    if !self.handle_request(request, &response_send) {
                        break;
                    }
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
                    self.handle_task(guard)?;
                    // We check and spawn an evict task regardless of whether `guard` is write, and
                    // we do so even before the client completes writing to the blob.  While this
                    // may seem a bit unusual, it should not pose any issues in practice.
                    self.check_then_spawn_evict(&mut evict_task);
                }

                Some(()) = OptionFuture::from(evict_task.as_mut().map(|guard| guard.join())) => {
                    let guard = evict_task.take().unwrap();
                    self.handle_task(guard)?;
                }

                _ = log_stats_interval.tick() => tracing::info!(stats = ?self.stats),
            }
        }
        tracing::info!(stats = ?self.stats);

        self.tasks.cancel();
        while let Some(guard) = self.tasks.join_next().await {
            self.handle_task(guard)?;
        }

        if let Some(mut guard) = evict_task {
            guard.cancel();
            guard.join().await;
            self.handle_task(guard)?;
        }

        Ok(())
    }

    fn handle_request(
        &self,
        request: Multipart,
        response_send: &UnboundedSender<Envelope<Frame>>,
    ) -> bool {
        macro_rules! push_response {
            ($response:expr $(,)?) => {
                if response_send.send($response).is_err() {
                    return false;
                }
            };
        }

        let request = match envelope::decode_request(request) {
            Ok(request) => request,
            Err(error) => {
                match error {
                    envelope::Error::InvalidFrameSequence { frames } => {
                        tracing::warn!(?frames, "invalid frame sequence");
                        // TODO: What else could we do?
                    }
                    envelope::Error::Decode { source, envelope } => {
                        tracing::warn!(error = %source, ?envelope, "decode error");
                        push_response!(envelope.map(|()| rep::invalid_request_error()));
                    }
                    envelope::Error::ExpectOneDataFrame { envelope } => {
                        tracing::warn!(?envelope, "expect exactly one data frame");
                        push_response!(envelope.map(|_| rep::invalid_request_error()));
                    }
                }
                return true;
            }
        };

        macro_rules! try_acquire {
            () => {
                match self.concurrency.clone().try_acquire_owned() {
                    Ok(permit) => permit,
                    Err(_) => {
                        push_response!(request.map(|_| rep::unavailable_error()));
                        return true;
                    }
                }
            };
        }

        tracing::debug!(request = ?&**request.data());
        match request.data().which() {
            // TODO: We do not `try_acquire` the semaphore for `ping` requests, so theoretically we
            // could experience denial of service due to `ping` requests, but that is probably not
            // an issue in practice.
            Ok(request::Ping(())) => push_response!(request.map(|_| rep::ping_response())),

            Ok(request::Read(Ok(read))) => {
                let permit = try_acquire!();

                let request = request.map(|data| data.map(|_| read));
                let response_send = response_send.clone();
                self.tasks
                    .push(Guard::spawn(move |cancel| {
                        Handler::new(self, request, response_send, permit)
                            .run_read(cancel)
                            .instrument(tracing::info_span!("ddcache/read"))
                    }))
                    .unwrap();
            }

            Ok(request::ReadMetadata(Ok(read_metadata))) => {
                let permit = try_acquire!();

                let request = request.map(|data| data.map(|_| read_metadata));
                let response_send = response_send.clone();
                self.tasks
                    .push(Guard::spawn(move |cancel| {
                        Handler::new(self, request, response_send, permit)
                            .run_read_metadata(cancel)
                            .instrument(tracing::info_span!("ddcache/read-metadata"))
                    }))
                    .unwrap();
            }

            Ok(request::Write(Ok(write))) => {
                let permit = try_acquire!();

                // `handler.write()` is not async, but for simplicity, we pretend it is.
                let request = request.map(|data| data.map(|_| write));
                let response_send = response_send.clone();
                self.tasks
                    .push(Guard::spawn(move |_| {
                        let handler = Handler::new(self, request, response_send, permit);
                        async move { handler.write() }
                            .instrument(tracing::info_span!("ddcache/write"))
                    }))
                    .unwrap();
            }

            Ok(request::Cancel(token)) => {
                if self.state.remove(token).is_some() {
                    tracing::debug!(token, "cancel");
                }
                push_response!(request.map(|_| rep::cancel_response()));
            }

            Ok(request::Read(Err(error)))
            | Ok(request::ReadMetadata(Err(error)))
            | Ok(request::Write(Err(error))) => {
                tracing::warn!(?request, %error, "decode error");
                push_response!(request.map(|_| rep::invalid_request_error()));
            }
            Err(error) => {
                tracing::warn!(?request, %error, "unknown request type");
                push_response!(request.map(|_| rep::invalid_request_error()));
            }
        }

        true
    }

    fn handle_task(&self, mut guard: Guard) -> Result<(), Error> {
        match guard.take_result() {
            Ok(result) => result,
            Err(error) => {
                tracing::warn!(%error, "handler task error");
                Ok(())
            }
        }
    }

    fn check_then_spawn_evict(&self, evict_task: &mut Option<Guard>) {
        if evict_task.is_none() && self.storage.size() > self.storage_size_hwm {
            *evict_task = Some(Guard::spawn(move |cancel| {
                evict(cancel, self.storage.clone(), self.storage_size_lwm)
                    .instrument(tracing::info_span!("ddcache/evict"))
            }));
        }
    }
}

macro_rules! check_result {
    ($self:ident, $result:expr $(,)?) => {
        $result
            .inspect_err(|error| {
                tracing::warn!(request = ?$self.request(), %error, "decode error");
            })
            .map_err(|_| rep::invalid_request_error())?
    };
}

macro_rules! check_max {
    ($self:ident, $size:expr, $max_size:ident, $error:ident $(,)?) => {
        if $size > $self.$max_size {
            tracing::warn!(request = ?$self.request(), "max size exceeded");
            return Err(rep::$error());
        }
    };
}

impl<R> Handler<R>
where
    R: fmt::Debug,
{
    fn new(
        server: &Actor,
        request: Envelope<Owner<Frame, R>>,
        response_send: UnboundedSender<Envelope<Frame>>,
        permit: OwnedSemaphorePermit,
    ) -> Self {
        Self {
            request: Some(request),
            response_send,
            max_key_size: server.max_key_size,
            max_metadata_size: server.max_metadata_size,
            max_blob_size: server.max_blob_size,

            blob_endpoints: server.blob_endpoints.clone(),

            state: server.state.clone(),
            storage: server.storage.clone(),

            permit: Some(permit),

            stats: server.stats.clone(),
        }
    }

    fn request(&self) -> &R {
        self.request.as_ref().unwrap().data()
    }

    fn check_key(&self, key: Result<&[u8], capnp::Error>) -> Result<Bytes, Frame> {
        let key = check_result!(self, key);
        if key.is_empty() {
            tracing::warn!(request = ?self.request(), "empty key");
            return Err(rep::invalid_request_error());
        }
        check_max!(self, key.len(), max_key_size, max_key_size_exceeded_error);
        Ok(Bytes::copy_from_slice(key))
    }

    fn check_metadata(
        &self,
        metadata: Result<&[u8], capnp::Error>,
    ) -> Result<Option<Bytes>, Frame> {
        let metadata = check_result!(self, metadata);
        check_max!(
            self,
            metadata.len(),
            max_metadata_size,
            max_metadata_size_exceeded_error,
        );
        Ok((!metadata.is_empty()).then(|| Bytes::copy_from_slice(metadata)))
    }

    fn check_size(&self, size: u32) -> Result<usize, Frame> {
        let size = usize::try_from(size).unwrap();
        check_max!(self, size, max_blob_size, max_blob_size_exceeded_error);
        Ok(size)
    }

    fn push_response(&mut self, response: Frame) {
        let response = self.request.take().unwrap().map(|_| response);
        let _ = self.response_send.send(response);
    }
}

impl Handler<request::read::Reader<'static>> {
    async fn run_read(self, cancel: Cancel) -> Result<(), Error> {
        tokio::select! {
            () = cancel.wait() => Ok(()),
            result = self.read() => result,
        }
    }

    async fn read(mut self) -> Result<(), Error> {
        // TODO: Pick a blob endpoint matching the client endpoint.
        let Some(endpoint) = self.blob_endpoints.first().copied() else {
            self.push_response(rep::ok_none_response());
            return Ok(());
        };

        let key = match self.check_key(self.request().get_key()) {
            Ok(key) => key,
            Err(response) => {
                self.push_response(response);
                return Ok(());
            }
        };

        let Some(reader) = self.storage.read(key).await else {
            self.stats.read_miss.fetch_add(1, Ordering::SeqCst);
            self.push_response(rep::ok_none_response());
            return Ok(());
        };
        self.stats.read_hit.fetch_add(1, Ordering::SeqCst);

        let metadata = reader.metadata();
        let size = reader.size();

        // No errors after this point.

        let permit = self.permit.take().unwrap();
        let token = self.state.insert_reader((reader, permit));
        tracing::debug!(token);
        self.push_response(rep::read_response(metadata, size, endpoint, token));

        Ok(())
    }
}

impl Handler<request::read_metadata::Reader<'static>> {
    async fn run_read_metadata(self, cancel: Cancel) -> Result<(), Error> {
        tokio::select! {
            () = cancel.wait() => Ok(()),
            result = self.read_metadata() => result,
        }
    }

    async fn read_metadata(mut self) -> Result<(), Error> {
        let key = match self.check_key(self.request().get_key()) {
            Ok(key) => key,
            Err(response) => {
                self.push_response(response);
                return Ok(());
            }
        };

        let Some(reader) = self.storage.read(key).await else {
            self.stats.read_miss.fetch_add(1, Ordering::SeqCst);
            self.push_response(rep::ok_none_response());
            return Ok(());
        };
        self.stats.read_hit.fetch_add(1, Ordering::SeqCst);

        self.push_response(rep::read_metadata_response(
            reader.metadata(),
            reader.size(),
        ));

        Ok(())
    }
}

impl Handler<request::write::Reader<'static>> {
    fn write(mut self) -> Result<(), Error> {
        // TODO: Pick a blob endpoint matching the client endpoint.
        let Some(endpoint) = self.blob_endpoints.first().copied() else {
            self.push_response(rep::ok_none_response());
            return Ok(());
        };

        let (key, metadata, size) = match try {
            let request = self.request();
            (
                self.check_key(request.get_key())?,
                self.check_metadata(request.get_metadata())?,
                self.check_size(request.get_size())?,
            )
        } {
            Ok(tuple) => tuple,
            Err(response) => {
                self.push_response(response);
                return Ok(());
            }
        };

        // TODO: Call `try_write` here because I believe that, as a cache, it is not very critical
        // to always update an entry.  Perhaps we should expose the interface to the client to
        // force an update?
        let Some(mut writer) = self.storage.try_write(key, /* truncate */ true) else {
            self.stats.write_lock_fail.fetch_add(1, Ordering::SeqCst);
            self.push_response(rep::ok_none_response());
            return Ok(());
        };
        self.stats.write_lock_succeed.fetch_add(1, Ordering::SeqCst);

        writer.set_metadata(metadata);

        // No errors after this point.

        let permit = self.permit.take().unwrap();
        let token = self.state.insert_writer((writer, size, permit));
        tracing::debug!(token);
        self.push_response(rep::write_response(endpoint, token));

        Ok(())
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
