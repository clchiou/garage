use std::collections::{HashMap, VecDeque};
use std::io;
use std::time::Duration;

use bytes::Bytes;
use capnp::message;
use capnp::serialize;
use futures::future::OptionFuture;
use futures::sink::SinkExt;
use futures::stream::TryStreamExt;
use snafu::prelude::*;
use tokio::sync::{mpsc, oneshot};
use tokio::time::{self, Instant};
use tracing::Instrument;
use zmq::{Context, DEALER};

use g1_tokio::task::{Cancel, JoinGuard};
use g1_zmq::duplex::Duplex;
use g1_zmq::envelope::{Envelope, Frame, Multipart};
use g1_zmq::Socket;

use ddcache_proto::ddcache_capnp::{request, response};
use ddcache_proto::envelope;
use ddcache_proto::{BlobEndpoint, Endpoint, Token};

use crate::blob::RemoteBlob;
use crate::error::{ConnectSnafu, DecodeSnafu, Error, UnexpectedResponseSnafu};

/// Protocol-specific errors.
#[derive(Debug, Snafu)]
enum ProtoError {
    #[snafu(display("invalid response: {source:?}"))]
    InvalidResponse { source: envelope::Error },
    #[snafu(display("invalid routing id: {response:?}"))]
    InvalidRoutingId { response: Envelope<Frame> },
}

impl From<ProtoError> for io::Error {
    fn from(error: ProtoError) -> Self {
        io::Error::other(error)
    }
}

type Request = (Frame, ResponseSend);
type RequestRecv = mpsc::Receiver<Request>;
type RequestSend = mpsc::Sender<Request>;

// It is a bit sloppy, but we use this type for both reading and writing to reduce boilerplate.
#[derive(Debug)]
pub(crate) struct Response {
    pub(crate) blob: Option<RemoteBlob>,
    pub(crate) metadata: Option<Bytes>,
    pub(crate) size: usize,
}

// Rust's orphan rule prevents us from implementing `TryFrom` for `Option<Response>`.
impl Response {
    fn try_from<'a>(response: &'a response::Reader<'a>) -> Result<Option<Self>, capnp::Error> {
        Ok(match response.which()? {
            response::Ping(()) => None,

            response::Read(read) => {
                let read = read?;
                let metadata = read.get_metadata()?;
                let endpoint = BlobEndpoint::try_from(read.get_endpoint()?)?;
                Some(Self {
                    blob: Some(RemoteBlob::new(endpoint, read.get_token())),
                    metadata: read
                        .has_metadata()
                        .then_some(Bytes::copy_from_slice(metadata)),
                    size: read.get_size().try_into().unwrap(),
                })
            }

            response::ReadMetadata(read_metadata) => {
                let read_metadata = read_metadata?;
                let metadata = read_metadata.get_metadata()?;
                Some(Self {
                    blob: None,
                    metadata: read_metadata
                        .has_metadata()
                        .then_some(Bytes::copy_from_slice(metadata)),
                    size: read_metadata.get_size().try_into().unwrap(),
                })
            }

            response::Write(write) => {
                let write = write?;
                let endpoint = BlobEndpoint::try_from(write.get_endpoint()?)?;
                Some(Self {
                    blob: Some(RemoteBlob::new(endpoint, write.get_token())),
                    metadata: None,
                    size: 0,
                })
            }

            response::Cancel(()) => None,
        })
    }
}

type ResponseResult = Result<Option<Response>, Error>;
type ResponseSend = oneshot::Sender<ResponseResult>;

type RoutingId = u64;

#[derive(Clone, Debug)]
pub(crate) struct Shard {
    endpoint: Endpoint,
    request_send: RequestSend,
    cancel: Cancel,
}

pub(crate) type ShardGuard = JoinGuard<Result<(), io::Error>>;

#[derive(Debug)]
struct Actor {
    cancel: Cancel,
    request_recv: RequestRecv,
    response_sends: ResponseSends,
    duplex: Duplex,
}

#[derive(Debug)]
struct ResponseSends {
    map: HashMap<RoutingId, ResponseSend>,
    // For now, we can use `VecDeque` because `timeout` is fixed.
    deadlines: VecDeque<(Instant, RoutingId)>,
    timeout: Duration,
}

impl Shard {
    pub(crate) fn connect(endpoint: Endpoint) -> Result<(Self, ShardGuard), Error> {
        tracing::info!(%endpoint, "connect");

        let (request_send, request_recv) = mpsc::channel(16);

        let socket: Result<Socket, io::Error> = try {
            let socket = Socket::try_from(Context::new().socket(DEALER)?)?;
            socket.set_linger(0)?; // Do NOT block the program exit!
            socket.connect(&endpoint)?;
            socket
        };
        let socket = socket.context(ConnectSnafu)?;

        let guard = {
            let endpoint = endpoint.clone();
            ShardGuard::spawn(move |cancel| {
                Actor::new(cancel, request_recv, socket.into())
                    .run()
                    .instrument(tracing::info_span!("ddcache/shard", %endpoint))
            })
        };

        Ok((
            Self {
                endpoint,
                request_send,
                cancel: guard.cancel_handle(),
            },
            guard,
        ))
    }

    pub(crate) fn disconnect(&self) {
        self.cancel.set();
    }

    pub(crate) fn endpoint(&self) -> Endpoint {
        self.endpoint.clone()
    }

    pub(crate) async fn ping(&self) -> Result<(), Error> {
        let response = self.request(|mut request| request.set_ping(())).await?;
        ensure!(response.is_none(), UnexpectedResponseSnafu);
        Ok(())
    }

    pub(crate) async fn read(&self, key: &[u8]) -> ResponseResult {
        self.request(|request| request.init_read().set_key(key))
            .await
    }

    pub(crate) async fn read_metadata(&self, key: &[u8]) -> ResponseResult {
        self.request(|request| request.init_read_metadata().set_key(key))
            .await
    }

    pub(crate) async fn write(
        &self,
        key: &[u8],
        metadata: Option<&[u8]>,
        size: usize,
    ) -> ResponseResult {
        self.request(|request| {
            let mut request = request.init_write();
            request.set_key(key);
            if let Some(metadata) = metadata {
                request.set_metadata(metadata);
            }
            request.set_size(size.try_into().unwrap());
        })
        .await
    }

    pub(crate) async fn cancel(&self, token: Token) -> Result<(), Error> {
        let response = self
            .request(|mut request| request.set_cancel(token))
            .await?;
        ensure!(response.is_none(), UnexpectedResponseSnafu);
        Ok(())
    }

    async fn request<F>(&self, init: F) -> ResponseResult
    where
        F: FnOnce(request::Builder),
    {
        let mut request = message::Builder::new_default();
        init(request.init_root::<request::Builder>());
        tracing::debug!(request = ?request.get_root_as_reader::<request::Reader>().unwrap());
        let request = Frame::from(serialize::write_message_to_words(&request));

        let (response_send, response_recv) = oneshot::channel();

        self.request_send
            .send((request, response_send))
            .await
            .map_err(|_| Error::Disconnected {
                endpoint: self.endpoint.clone(),
            })?;

        response_recv.await.map_err(|_| Error::Disconnected {
            endpoint: self.endpoint.clone(),
        })?
    }
}

impl Actor {
    fn new(cancel: Cancel, request_recv: RequestRecv, duplex: Duplex) -> Self {
        Self {
            cancel,
            request_recv,
            response_sends: ResponseSends::new(),
            duplex,
        }
    }

    async fn run(mut self) -> Result<(), io::Error> {
        let mut deadline = None;
        tokio::pin! { let timeout = OptionFuture::from(None); }

        loop {
            let next_deadline = self.response_sends.next_deadline();
            if deadline != next_deadline {
                deadline = next_deadline;
                timeout.set(deadline.map(time::sleep_until).into());
            }

            tokio::select! {
                () = self.cancel.wait() => break,

                request = self.request_recv.recv() => {
                    let Some(request) = request else { break };
                    // Block the actor loop on `duplex.send` because it is probably desirable to
                    // derive back pressure from this point.
                    self.handle_request(request).await?;
                }

                response = self.duplex.try_next() => {
                    let Some(response) = response? else { break };
                    self.handle_response(response)?;
                }

                Some(()) = &mut timeout => {
                    self.response_sends.remove_expired(Instant::now());
                    deadline = None;
                    timeout.set(None.into());
                }
            }
        }

        Ok(())
    }

    async fn handle_request(&mut self, (request, response_send): Request) -> Result<(), io::Error> {
        let routing_id = self.response_sends.insert(response_send);
        let request = Envelope::new(
            vec![Frame::from(routing_id.to_be_bytes().as_slice())],
            request,
        );
        self.duplex.send(request.into()).await
    }

    fn handle_response(&mut self, frames: Multipart) -> Result<(), io::Error> {
        let response = envelope::decode(frames).context(InvalidResponseSnafu)?;

        let routing_id = response.routing_id();
        ensure!(
            routing_id.len() == 1 && routing_id[0].len() == 8,
            InvalidRoutingIdSnafu { response },
        );
        let routing_id = RoutingId::from_be_bytes((*routing_id[0]).try_into().unwrap());

        let Some(response_send) = self.response_sends.remove(routing_id) else {
            tracing::debug!(routing_id, "response_send not found");
            return Ok(());
        };

        let _ = response_send.send(self.decode_response(response));

        Ok(())
    }

    fn decode_response(&self, response: Envelope<Frame>) -> ResponseResult {
        let result: Result<_, capnp::Error> = try {
            match &**envelope::decode_response(response)?.data() {
                Ok(Some(response)) => Ok(Response::try_from(response)?),
                Ok(None) => Ok(None),
                Err(error) => Err(Error::try_from(error)?),
            }
        };
        result.context(DecodeSnafu)?
    }
}

impl ResponseSends {
    fn new() -> Self {
        Self {
            map: HashMap::new(),
            deadlines: VecDeque::new(),
            timeout: *crate::request_timeout(),
        }
    }

    fn next_routing_id(&self) -> RoutingId {
        for _ in 0..4 {
            let routing_id = rand::random();
            // It is a small detail, but we do not generate 0.
            if routing_id != 0 && !self.map.contains_key(&routing_id) {
                return routing_id;
            }
        }
        std::panic!("cannot generate random routing id")
    }

    fn next_deadline(&mut self) -> Option<Instant> {
        self.deadlines.front().map(|(deadline, _)| *deadline)
    }

    fn remove_expired(&mut self, now: Instant) {
        while let Some((deadline, routing_id)) = self.deadlines.front().copied() {
            if deadline <= now {
                if let Some(response_send) = self.map.remove(&routing_id) {
                    tracing::warn!(routing_id, "expire");
                    let _ = response_send.send(Err(Error::RequestTimeout));
                }
                self.deadlines.pop_front();
            } else {
                break;
            }
        }
    }

    fn insert(&mut self, response_send: ResponseSend) -> RoutingId {
        let routing_id = self.next_routing_id();
        let deadline = Instant::now() + self.timeout;
        assert!(self.map.insert(routing_id, response_send).is_none());
        self.deadlines.push_back((deadline, routing_id));
        routing_id
    }

    fn remove(&mut self, routing_id: RoutingId) -> Option<ResponseSend> {
        self.map.remove(&routing_id)
    }
}
