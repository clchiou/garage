mod handle;
mod refresh;

use std::collections::{BTreeSet, HashMap};
use std::io::Error;
use std::net::SocketAddr;
use std::panic;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use bitvec::prelude::*;
use tokio::{sync::mpsc, task::JoinError, time};
use tracing::Instrument;

use g1_base::sync::MutexExt;
use g1_tokio::task::JoinQueue;

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

#[derive(Debug)]
pub(crate) struct Server {
    inner: Arc<Inner>,
    token_src: Arc<TokenSource>,
    // For now, we are spawning handlers and refreshers onto the same queue.
    tasks: JoinQueue<Result<(), Error>>,
    kbucket_full_recv: mpsc::Receiver<KBucketFull>,
    kbucket_full_send: mpsc::Sender<KBucketFull>,
    kbucket_refresh_period: Duration,
}

// Declared as `pub(crate)` to be shared with `agent`.
#[derive(Debug)]
pub(crate) struct Inner {
    pub(crate) self_id: NodeId,
    // NOTE: There is no deadlock because `Handler::handle_query` always acquires `routing` before
    // `peers`.
    // TODO: Relying on this locking convention feels fragile.  What should we do instead?
    pub(crate) routing: Mutex<RoutingTable>,
    // Use `BTreeSet` because it seems nicer to return an ordered peer set.
    pub(crate) peers: Mutex<HashMap<InfoHash, BTreeSet<SocketAddr>>>,
    pub(crate) reqrep: ReqRep,
}

impl Server {
    pub(crate) fn new(self_id: NodeId, reqrep: ReqRep) -> Self {
        let (kbucket_full_send, kbucket_full_recv) =
            mpsc::channel(*crate::kbucket_full_queue_size());
        Self {
            inner: Arc::new(Inner::new(self_id, reqrep)),
            token_src: Arc::new(TokenSource::new()),
            tasks: JoinQueue::new(),
            kbucket_full_recv,
            kbucket_full_send,
            kbucket_refresh_period: *crate::refresh_period(),
        }
    }

    pub(crate) fn inner(&self) -> Arc<Inner> {
        self.inner.clone()
    }

    pub(crate) async fn run(mut self) -> Result<(), Error> {
        let mut kbucket_refresh_interval = time::interval(self.kbucket_refresh_period);
        loop {
            tokio::select! {
                request = self.inner.reqrep.accept() => {
                    match request {
                        Some(request) => self.spawn_handler(request),
                        None => break,
                    }
                }
                join_result = self.tasks.join_next() => {
                    // We can call `unwrap` because `tasks` is not closed in the main loop.
                    join_task(join_result.unwrap());
                }
                full = self.kbucket_full_recv.recv() => {
                    // We can call `unwrap` because `kbucket_full_recv` is never closed.
                    self.spawn_node_refresher(full.unwrap());
                }
                _ = kbucket_refresh_interval.tick() => {
                    self.spawn_kbucket_refresher(Instant::now());
                }
            }
        }

        self.tasks.close();
        let _ = time::timeout(*crate::grace_period() / 2, async {
            while let Some(join_result) = self.tasks.join_next().await {
                join_task(join_result);
            }
        })
        .await;
        self.tasks.abort_all_then_join().await;

        Ok(())
    }

    fn spawn_handler(&self, ((endpoint, request), response_send): (Incoming, Sender)) {
        let socket_addr = endpoint.0;
        let handler = Handler::new(
            self.inner.clone(),
            self.token_src.clone(),
            self.kbucket_full_send.clone(),
            endpoint,
            request,
            response_send,
        );
        let handler_run = handler
            .run()
            .instrument(tracing::info_span!("dht/peer", peer_endpoint = ?socket_addr));
        // We can call `unwrap` because `tasks` is not closed in the main loop.
        let _ = self.tasks.spawn(handler_run).unwrap();
    }

    fn spawn_node_refresher(&self, (incumbents, candidate): KBucketFull) {
        let contact_info = candidate.contact_info.clone();
        let refresher = NodeRefresher::new(self.inner.clone(), incumbents, candidate);
        let refresher_run = refresher
            .run()
            .instrument(tracing::info_span!("dht/refresh", candidate = ?contact_info));
        // We can call `unwrap` because `tasks` is not closed in the main loop.
        let _ = self.tasks.spawn(refresher_run).unwrap();
    }

    fn spawn_kbucket_refresher(&self, now: Instant) {
        let mut ids = Vec::new();
        let should_refresh = now - self.kbucket_refresh_period;
        for (kbucket, prefix) in self.inner.routing.must_lock().iter() {
            if let Some(recently_seen) = kbucket.recently_seen() {
                if recently_seen <= should_refresh {
                    ids.push(random_id(prefix));
                }
            }
        }
        // We can call `unwrap` because `tasks` is not closed in the main loop.
        let _ = self
            .tasks
            .spawn(KBucketRefresher::new(self.inner.clone(), ids).run())
            .unwrap();
    }
}

impl Drop for Server {
    fn drop(&mut self) {
        self.tasks.abort_all();
    }
}

fn join_task(join_result: Result<Result<(), Error>, JoinError>) {
    match join_result {
        Ok(result) => {
            if let Err(error) = result {
                tracing::warn!(?error, "dht task error");
            }
        }
        Err(join_error) => {
            if join_error.is_panic() {
                panic::resume_unwind(join_error.into_panic());
            }
            assert!(join_error.is_cancelled());
            tracing::warn!("dht task is cancelled");
        }
    }
}

fn random_id(prefix: KBucketPrefix) -> NodeId {
    let mut id: [u8; NODE_ID_SIZE] = rand::random();
    id.view_bits_mut()[0..prefix.len()].copy_from_bitslice(&prefix);
    NodeId::new(id)
}

impl Inner {
    fn new(self_id: NodeId, reqrep: ReqRep) -> Self {
        let routing = Mutex::new(RoutingTable::new(self_id.clone()));
        Self {
            self_id,
            routing,
            peers: Mutex::new(HashMap::new()),
            reqrep,
        }
    }

    pub(crate) fn connect(&self, peer_endpoint: SocketAddr) -> Client {
        Client::new(&self.reqrep, self.self_id.clone(), peer_endpoint)
    }
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
