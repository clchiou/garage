//! Node Agent
//!
//! I refer to it as an agent because it does more than a server; it not only serves requests from
//! peers but also actively sends requests to peers.

mod handle;
mod refresh;

use std::collections::{BTreeSet, HashMap};
use std::io::Error;
use std::net::SocketAddr;
use std::panic;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use bitvec::prelude::*;
use tokio::{sync::mpsc, time};

use g1_base::sync::MutexExt;
use g1_tokio::task::{Cancel, JoinGuard, JoinQueue};

use bittorrent_base::InfoHash;

use crate::{
    reqrep::{Client, Incoming, ReqRep, Sender},
    routing::{KBucketFull, KBucketPrefix, RoutingTable},
    token::TokenSource,
    NodeId, NODE_ID_SIZE,
};

use self::{
    handle::Handler,
    refresh::{KBucketRefresher, NodeRefresher},
};

// TODO: We are currently declaring stub fields as `pub(crate)` for the ease of implementation.
#[derive(Debug)]
pub(crate) struct Agent {
    pub(crate) self_id: NodeId,
    // NOTE: There is no deadlock because `Handler::handle_query` always acquires `routing` before
    // `peers`.
    // TODO: Relying on this locking convention feels fragile.  What should we do instead?
    pub(crate) routing: Mutex<RoutingTable>,
    // Use `BTreeSet` because it seems nicer to return an ordered peer set.
    pub(crate) peers: Mutex<HashMap<InfoHash, BTreeSet<SocketAddr>>>,
    pub(crate) reqrep: ReqRep,
}

pub(crate) type AgentGuard = JoinGuard<Result<(), Error>>;

// TODO: For now, the agent stub doubles as the node state.
pub(crate) type NodeState = Arc<Agent>;

#[derive(Debug)]
struct Actor {
    cancel: Cancel,
    state: NodeState,
    token_src: Arc<TokenSource>,
    // For now, we are spawning handlers and refreshers onto the same queue.
    tasks: JoinQueue<Result<(), Error>>,
    kbucket_full_recv: mpsc::Receiver<KBucketFull>,
    kbucket_full_send: mpsc::Sender<KBucketFull>,
    kbucket_refresh_period: Duration,
}

impl Agent {
    pub(crate) fn spawn(self_id: NodeId, reqrep: ReqRep) -> (Arc<Self>, AgentGuard) {
        tracing::info!(?self_id);
        let this = Arc::new(Self::new(self_id, reqrep));
        let state = this.clone();
        let guard = JoinGuard::spawn(move |cancel| Actor::new(cancel, state).run());
        (this, guard)
    }

    fn new(self_id: NodeId, reqrep: ReqRep) -> Self {
        Self {
            self_id: self_id.clone(),
            routing: Mutex::new(RoutingTable::new(self_id)),
            peers: Mutex::new(HashMap::new()),
            reqrep,
        }
    }

    pub(crate) fn connect(&self, peer_endpoint: SocketAddr) -> Client {
        Client::new(self.reqrep.clone(), self.self_id.clone(), peer_endpoint)
    }
}

impl Actor {
    fn new(cancel: Cancel, state: NodeState) -> Self {
        let (kbucket_full_send, kbucket_full_recv) =
            mpsc::channel(*crate::kbucket_full_queue_size());
        Self {
            cancel: cancel.clone(),
            state,
            token_src: Arc::new(TokenSource::new()),
            tasks: JoinQueue::with_cancel(cancel),
            kbucket_full_recv,
            kbucket_full_send,
            kbucket_refresh_period: *crate::refresh_period(),
        }
    }

    // It returns `Result<(), Error>` to maintain compatibility with `JoinArray::shutdown`.
    async fn run(mut self) -> Result<(), Error> {
        let mut kbucket_refresh_interval = time::interval(self.kbucket_refresh_period);
        loop {
            tokio::select! {
                () = self.cancel.wait() => break,

                request = self.state.reqrep.accept() => {
                    let Some(request) = request else { break };
                    self.spawn_handler(request);
                }
                guard = self.tasks.join_next() => {
                    let Some(guard) = guard else { break };
                    Self::log_task_result(guard);
                }
                full = self.kbucket_full_recv.recv() => {
                    // We can call `unwrap` because `kbucket_full_recv` is never closed.
                    self.spawn_node_refresher(full.unwrap());
                }
                // We prefer the actual current time over the deadline returned by `tick`.
                _ = kbucket_refresh_interval.tick() => {
                    self.spawn_kbucket_refresher(Instant::now());
                }
            }
        }
        self.tasks.cancel();
        while let Some(guard) = self.tasks.join_next().await {
            Self::log_task_result(guard);
        }
        Ok(())
    }

    fn spawn_handler(&self, ((endpoint, request), response_send): (Incoming, Sender)) {
        self.push_task(JoinGuard::spawn(move |cancel| {
            Handler::new(
                cancel,
                self.state.clone(),
                self.token_src.clone(),
                self.kbucket_full_send.clone(),
                endpoint,
                request,
                response_send,
            )
            .run()
        }));
    }

    fn spawn_node_refresher(&self, (incumbents, candidate): KBucketFull) {
        self.push_task(JoinGuard::spawn(move |cancel| {
            NodeRefresher::new(cancel, self.state.clone(), incumbents, candidate).run()
        }));
    }

    fn spawn_kbucket_refresher(&self, now: Instant) {
        let mut ids = Vec::new();
        let should_refresh = now - self.kbucket_refresh_period;
        for (kbucket, prefix) in self.state.routing.must_lock().iter() {
            if let Some(recently_seen) = kbucket.recently_seen() {
                if recently_seen <= should_refresh {
                    ids.push(random_id(prefix));
                }
            }
        }
        self.push_task(JoinGuard::spawn(move |cancel| {
            KBucketRefresher::new(cancel, self.state.clone(), ids).run()
        }));
    }

    fn push_task(&self, guard: JoinGuard<Result<(), Error>>) {
        // `tasks.push` returns an error if `tasks` is cancelled, and in this case, we may ignore
        // the error.
        let _ = self.tasks.push(guard);
    }

    fn log_task_result(mut guard: JoinGuard<Result<(), Error>>) {
        if let Err(error) = guard.take_result().map_err(Error::from).flatten() {
            tracing::warn!(%error, "node agent task error");
        }
    }
}

fn random_id(prefix: KBucketPrefix) -> NodeId {
    let mut id: [u8; NODE_ID_SIZE] = rand::random();
    id.view_bits_mut()[0..prefix.len()].copy_from_bitslice(&prefix);
    NodeId::new(id)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_random_id() {
        for expect in [NodeId::min(), NodeId::max()] {
            for i in 0..=NODE_ID_SIZE * 8 {
                let id = random_id(KBucketPrefix::from(&expect.bits()[..i]));
                assert_eq!(&id.bits()[..i], &expect.bits()[..i]);
                // It has sufficient bits to ensure that an `assert_ne` is very, very unlikely to
                // fail randomly.
                if NODE_ID_SIZE * 8 - i > 30 {
                    assert_ne!(&id.bits()[i..], &expect.bits()[i..]);
                }
            }
        }
    }
}
