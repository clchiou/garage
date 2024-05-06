use std::collections::{HashMap, VecDeque};
use std::io;
use std::time::Duration;

use bytes::Bytes;
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

use ddcache_rpc::envelope;
use ddcache_rpc::rpc_capnp::response;
use ddcache_rpc::{BlobMetadata, Endpoint, Timestamp, Token};

use crate::blob::RemoteBlob;
use crate::error::{ConnectSnafu, DecodeSnafu, Error, UnexpectedResponseSnafu};

/// Protocol-specific errors.
#[derive(Debug, Snafu)]
enum ProtoError {
    #[snafu(display("invalid response: {source}"))]
    InvalidResponse { source: envelope::Error },
    #[snafu(display("invalid routing id: {response:?}"))]
    InvalidRoutingId { response: Envelope<Frame> },
}

type Request = (ddcache_rpc::Request, ResponseSend);
type RequestRecv = mpsc::Receiver<Request>;
type RequestSend = mpsc::Sender<Request>;

// It is a bit sloppy, but we use this type for both reading and writing to reduce boilerplate.
#[derive(Debug)]
pub(crate) struct Response {
    pub(crate) metadata: Option<BlobMetadata>,
    pub(crate) blob: Option<RemoteBlob>,
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

    pub(crate) async fn cancel(&self, token: Token) -> Result<(), Error> {
        let response = self.request(ddcache_rpc::Request::Cancel(token)).await?;
        ensure!(response.is_none(), UnexpectedResponseSnafu);
        Ok(())
    }

    pub(crate) async fn read(&self, key: Bytes) -> ResponseResult {
        self.request(ddcache_rpc::Request::Read { key }).await
    }

    pub(crate) async fn read_metadata(&self, key: Bytes) -> ResponseResult {
        self.request(ddcache_rpc::Request::ReadMetadata { key })
            .await
    }

    pub(crate) async fn write(
        &self,
        key: Bytes,
        metadata: Option<Bytes>,
        size: usize,
        expire_at: Option<Timestamp>,
    ) -> ResponseResult {
        self.request(ddcache_rpc::Request::Write {
            key,
            metadata,
            size,
            expire_at,
        })
        .await
    }

    pub(crate) async fn write_metadata(
        &self,
        key: Bytes,
        metadata: Option<Option<Bytes>>,
        expire_at: Option<Option<Timestamp>>,
    ) -> ResponseResult {
        self.request(ddcache_rpc::Request::WriteMetadata {
            key,
            metadata,
            expire_at,
        })
        .await
    }

    pub(crate) async fn remove(&self, key: Bytes) -> ResponseResult {
        self.request(ddcache_rpc::Request::Remove { key }).await
    }

    async fn request(&self, request: ddcache_rpc::Request) -> ResponseResult {
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
        tracing::debug!(?request);
        let routing_id = self.response_sends.insert(response_send);
        let request = Envelope::new(
            vec![Frame::from(routing_id.to_be_bytes().as_slice())],
            Frame::from(Vec::<u8>::from(request)),
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

        let response = self.decode(response);
        tracing::debug!(?response);

        let Some(response_send) = self.response_sends.remove(routing_id) else {
            tracing::debug!(routing_id, "response_send not found");
            return Ok(());
        };

        let _ = response_send.send(response);
        Ok(())
    }

    fn decode(&self, response: Envelope<Frame>) -> ResponseResult {
        let result: Result<_, capnp::Error> = try {
            match **envelope::decode_response(response)?.data() {
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

impl From<ProtoError> for io::Error {
    fn from(error: ProtoError) -> Self {
        io::Error::other(error)
    }
}

// Rust's orphan rule prevents us from implementing `TryFrom` for `Option<Response>`.
impl Response {
    fn try_from(response: response::Reader) -> Result<Option<Self>, capnp::Error> {
        Ok(match ddcache_rpc::Response::try_from(response)? {
            ddcache_rpc::Response::Cancel => None,
            ddcache_rpc::Response::Read { metadata, blob } => Some(Self {
                metadata: Some(metadata),
                blob: Some(blob.into()),
            }),
            ddcache_rpc::Response::ReadMetadata { metadata } => Some(Self {
                metadata: Some(metadata),
                blob: None,
            }),
            ddcache_rpc::Response::Write { blob } => Some(Self {
                metadata: None,
                blob: Some(blob.into()),
            }),
            ddcache_rpc::Response::WriteMetadata { metadata } => Some(Self {
                metadata: Some(metadata),
                blob: None,
            }),
            ddcache_rpc::Response::Remove { metadata } => Some(Self {
                metadata: Some(metadata),
                blob: None,
            }),
        })
    }
}
