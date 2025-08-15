use std::sync::Arc;

use tokio::time;

use g1_tokio::task::JoinGuard;

use bt_base::NodeId;

use crate::insert::Insert;
use crate::lookup::Lookup;
use crate::table::Table;

struct Refresher {
    self_id: NodeId,
    table: Arc<Table>,
    lookup: Lookup,
    insert: Insert,
}

pub(crate) type RefresherGuard = JoinGuard<()>;

pub(crate) fn spawn(
    self_id: NodeId,
    table: Arc<Table>,
    lookup: Lookup,
    insert: Insert,
) -> RefresherGuard {
    RefresherGuard::spawn(move |cancel| {
        let mut refresher = RefresherLoop::new(
            cancel,
            Refresher {
                self_id,
                table,
                lookup,
                insert,
            },
        );
        async move { refresher.run().await }
    })
}

#[g1_actor::actor(loop_(react = { let () = self.table.written() ; }))]
impl Refresher {
    #[actor::loop_(react = {
        let Some(bit_index) = self.wait_refresh();
        self.refresh(bit_index).await
    })]
    async fn wait_refresh(&self) -> Option<usize> {
        let deadline = self.table.read().peek_refresh_deadline()?;
        time::sleep_until(deadline).await;
        self.table.write().next_refresh()
    }

    async fn refresh(&self, bit_index: usize) {
        let target = self.self_id.invert_then_random_suffix(bit_index);
        tracing::info!(%bit_index, %target, "bucket timeout; refresh");
        let Some(lookup_nodes) = self.lookup.lookup_nodes(target.clone()).await else {
            tracing::warn!(%bit_index, %target, "refresh: lookup_nodes no result");
            return;
        };
        for (node, last_ok) in lookup_nodes {
            self.insert.insert(node, last_ok).await;
        }
    }
}
