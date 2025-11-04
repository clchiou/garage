use std::hash::Hash;

use g1_tokio::time::set::naive::FixedDelaySet;

use bt_base::{BlockRange, ConnId, InfoHash};

pub(super) trait FixedDelaySetExt {
    fn remove_peer(&mut self, conn_id: &ConnId);

    fn remove_torrent(&mut self, info_hash: InfoHash);
}

impl FixedDelaySetExt for FixedDelaySet<(ConnId, BlockRange)> {
    fn remove_peer(&mut self, conn_id: &ConnId) {
        remove_if(self, |(id, _)| id == conn_id);
    }

    fn remove_torrent(&mut self, info_hash: InfoHash) {
        remove_if(self, |(conn_id, _)| conn_id.info_hash == info_hash);
    }
}

impl FixedDelaySetExt for FixedDelaySet<ConnId> {
    fn remove_peer(&mut self, conn_id: &ConnId) {
        self.remove(conn_id);
    }

    fn remove_torrent(&mut self, info_hash: InfoHash) {
        remove_if(self, |conn_id| conn_id.info_hash == info_hash);
    }
}

fn remove_if<T, F>(set: &mut FixedDelaySet<T>, f: F)
where
    // TODO: Remove this after `FixedDelaySet` provides a proper `retain`.
    T: Clone + Eq + Hash,
    F: Fn(&T) -> bool,
{
    set.retain(|value| !f(value));
}
