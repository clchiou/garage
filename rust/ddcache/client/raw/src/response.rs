use std::collections::{HashMap, VecDeque};
use std::time::Duration;

use tokio::sync::oneshot;
use tokio::time::Instant;

use ddcache_rpc::rpc_capnp::response;
use ddcache_rpc::BlobMetadata;

use crate::blob::RemoteBlob;
use crate::error::Error;

// It is a bit sloppy, but we use this type instead of `ddcache_rpc::Response` to reduce
// boilerplate.
#[derive(Debug)]
pub struct Response {
    pub metadata: Option<BlobMetadata>,
    pub blob: Option<RemoteBlob>,
}

pub type ResponseResult = Result<Option<Response>, Error>;

#[derive(Debug)]
pub(crate) struct ResponseSends {
    map: HashMap<RoutingId, ResponseSend>,
    // For now, we can use `VecDeque` because `timeout` is fixed.
    deadlines: VecDeque<(Instant, RoutingId)>,
    timeout: Duration,
}

pub(crate) type RoutingId = u64;
pub(crate) type ResponseSend = oneshot::Sender<ResponseResult>;

// Rust's orphan rule prevents us from implementing `TryFrom` for `Option<Response>`.
impl Response {
    pub(crate) fn try_from(response: response::Reader) -> Result<Option<Self>, capnp::Error> {
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
            ddcache_rpc::Response::Pull { metadata, blob } => Some(Self {
                metadata: Some(metadata),
                blob: Some(blob.into()),
            }),
            ddcache_rpc::Response::Push { blob } => Some(Self {
                metadata: None,
                blob: Some(blob.into()),
            }),
        })
    }
}

impl ResponseSends {
    pub(crate) fn new() -> Self {
        Self {
            map: HashMap::new(),
            deadlines: VecDeque::new(),
            timeout: *crate::request_timeout(),
        }
    }

    pub(crate) fn next_routing_id(&self) -> RoutingId {
        for _ in 0..4 {
            let routing_id = rand::random();
            // It is a small detail, but we do not generate 0.
            if routing_id != 0 && !self.map.contains_key(&routing_id) {
                return routing_id;
            }
        }
        std::panic!("cannot generate random routing id")
    }

    pub(crate) fn next_deadline(&mut self) -> Option<Instant> {
        self.deadlines.front().map(|(deadline, _)| *deadline)
    }

    pub(crate) fn remove_expired(&mut self, now: Instant) {
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

    pub(crate) fn insert(&mut self, response_send: ResponseSend) -> RoutingId {
        let routing_id = self.next_routing_id();
        let deadline = Instant::now() + self.timeout;
        assert!(self.map.insert(routing_id, response_send).is_none());
        self.deadlines.push_back((deadline, routing_id));
        routing_id
    }

    pub(crate) fn remove(&mut self, routing_id: RoutingId) -> Option<ResponseSend> {
        self.map.remove(&routing_id)
    }
}
