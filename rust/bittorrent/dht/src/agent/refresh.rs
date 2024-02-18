use std::io::Error;

use tracing::Instrument;

use g1_base::sync::MutexExt;
use g1_tokio::task::Joiner;

use crate::{kbucket::KBucketItem, lookup::Lookup, NodeContactInfo, NodeId};

use super::NodeState;

#[derive(Debug)]
pub(super) struct NodeRefresher {
    state: NodeState,
    incumbents: Vec<NodeContactInfo>,
    candidate: KBucketItem,
    concurrency: usize,
}

impl NodeRefresher {
    pub(super) fn new(
        state: NodeState,
        incumbents: Vec<NodeContactInfo>,
        candidate: KBucketItem,
    ) -> Self {
        Self::with_concurrency(state, incumbents, candidate, *crate::alpha())
    }

    fn with_concurrency(
        state: NodeState,
        incumbents: Vec<NodeContactInfo>,
        candidate: KBucketItem,
        concurrency: usize,
    ) -> Self {
        Self {
            state,
            incumbents,
            candidate,
            concurrency,
        }
    }

    // When a bucket is full, BEP 5 specifies that questionable nodes are pinged twice, and then a
    // bad node is removed to save space for the new node.  For the sake of simplicity, we deviate
    // from BEP 5: Every node in the bucket is pinged, and it is only pinged once.
    pub(super) async fn run(self) -> Result<(), Error> {
        let Self {
            state,
            incumbents,
            candidate,
            concurrency,
        } = self;

        let mut tasks = Joiner::new(
            incumbents.into_iter().map(|incumbent| {
                let state = state.clone();
                async move {
                    let client = state.connect(incumbent.endpoint);
                    (incumbent, client.ping().await)
                }
            }),
            concurrency,
        );

        let mut have_removed_nodes = false;
        while let Some(join_result) = tasks.join_next().await {
            // We can call `unwrap` because we do not expect tasks to crash.
            let (incumbent, result) = join_result.unwrap();
            if let Err(error) = result {
                tracing::info!(
                    ?incumbent,
                    ?error,
                    "ping node error; remove from routing table",
                );
                if state.routing.must_lock().remove(&incumbent).is_some() {
                    have_removed_nodes = true;
                }
            }
        }

        if have_removed_nodes {
            if let Err((_, candidate)) = state.routing.must_lock().insert(candidate) {
                tracing::warn!(
                    candidate = ?candidate.contact_info,
                    "discard candidate because kbucket is still full after removing nodes",
                );
            }
        }

        Ok(())
    }
}

#[derive(Debug)]
pub(super) struct KBucketRefresher {
    state: NodeState,
    ids: Vec<NodeId>,
}

impl KBucketRefresher {
    pub(super) fn new(state: NodeState, ids: Vec<NodeId>) -> Self {
        Self { state, ids }
    }

    pub(super) async fn run(self) -> Result<(), Error> {
        let Self { state, ids } = self;
        let lookup = Lookup::new(state.clone());
        // Refresh buckets serially.
        for id in ids {
            let nodes = lookup
                .lookup_nodes(id.clone())
                .instrument(tracing::info_span!("dht/refresh", ?id))
                .await;
            {
                let mut routing = state.routing.must_lock();
                for node in nodes {
                    routing.must_insert(KBucketItem::new(node));
                }
            }
        }
        Ok(())
    }
}
