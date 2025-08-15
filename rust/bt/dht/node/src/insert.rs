use std::sync::Arc;

use tokio::time::Instant;

use bt_dht_proto::NodeInfo;
use bt_dht_reqrep::ReqRep;

use crate::table::Table;

#[derive(Clone, Debug)]
pub(crate) struct Insert {
    table: Arc<Table>,
    reqrep: ReqRep,
}

impl Insert {
    pub(crate) fn new(table: Arc<Table>, reqrep: ReqRep) -> Self {
        Self { table, reqrep }
    }

    pub(crate) async fn insert(&self, node: NodeInfo, last_ok: Option<Instant>) {
        let Err(mut full) = self.table.write().insert(node, last_ok) else {
            return;
        };

        // If the bucket is full and the new node was not obtained from a successful query, it is
        // probably better to just drop it.
        if last_ok.is_none() {
            return;
        }

        while let Some(stale) = full.next() {
            // BEP 5 suggests considering a stale node non-responding when it fails two consecutive
            // pings.
            let mut result = self.reqrep.ping(stale.clone()).await;
            if result.is_err() {
                result = self.reqrep.ping(stale.clone()).await;
            }

            let table = &mut self.table.write();
            match result {
                Ok(()) => full.ok(table, stale),
                Err(ping_error) => {
                    tracing::debug!(?stale, %ping_error, "bucket full; replace stale");
                    match full.err(table, stale.id) {
                        Some(continue_) => full = continue_,
                        None => break,
                    }
                }
            }
        }
    }
}
