use std::io::Error;
use std::sync::Arc;

use tracing::Instrument;

use g1_base::sync::MutexExt;
use g1_tokio::task::Joiner;

use crate::{kbucket::KBucketItem, lookup::Lookup, NodeContactInfo, NodeId};

use super::Inner;

#[derive(Debug)]
pub(super) struct NodeRefresher {
    inner: Arc<Inner>,
    incumbents: Vec<NodeContactInfo>,
    candidate: KBucketItem,
    concurrency: usize,
}

impl NodeRefresher {
    pub(super) fn new(
        inner: Arc<Inner>,
        incumbents: Vec<NodeContactInfo>,
        candidate: KBucketItem,
    ) -> Self {
        Self::with_concurrency(inner, incumbents, candidate, *crate::alpha())
    }

    fn with_concurrency(
        inner: Arc<Inner>,
        incumbents: Vec<NodeContactInfo>,
        candidate: KBucketItem,
        concurrency: usize,
    ) -> Self {
        Self {
            inner,
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
            inner,
            incumbents,
            candidate,
            concurrency,
        } = self;

        let mut tasks = Joiner::new(
            incumbents.into_iter().map(|incumbent| {
                let inner = inner.clone();
                async move {
                    let client = inner.connect(incumbent.endpoint);
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
                if inner.routing.must_lock().remove(&incumbent).is_some() {
                    have_removed_nodes = true;
                }
            }
        }

        if have_removed_nodes {
            if let Err((_, candidate)) = inner.routing.must_lock().insert(candidate) {
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
    inner: Arc<Inner>,
    ids: Vec<NodeId>,
}

impl KBucketRefresher {
    pub(super) fn new(inner: Arc<Inner>, ids: Vec<NodeId>) -> Self {
        Self { inner, ids }
    }

    pub(super) async fn run(self) -> Result<(), Error> {
        let Self { inner, ids } = self;
        let lookup = Lookup::new(inner.clone());
        // Refresh buckets serially.
        for id in ids {
            let nodes = lookup
                .lookup_nodes(id.clone())
                .instrument(tracing::info_span!("dht/refresh", ?id))
                .await;
            {
                let mut routing = inner.routing.must_lock();
                for node in nodes {
                    routing.must_insert(KBucketItem::new(node));
                }
            }
        }
        Ok(())
    }
}
