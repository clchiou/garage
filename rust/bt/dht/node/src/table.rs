use std::ops::{Deref, DerefMut};
use std::sync::{Mutex, MutexGuard};

use tokio::sync::Notify;

use g1_base::sync::MutexExt;

use bt_base::NodeId;

#[derive(Debug)]
pub(crate) struct Table {
    table: Mutex<bt_dht_route::Table>,
    written: Notify,
}

#[derive(Debug)]
pub(crate) struct ReadGuard<'a> {
    guard: MutexGuard<'a, bt_dht_route::Table>,
}

#[derive(Debug)]
pub(crate) struct WriteGuard<'a> {
    guard: MutexGuard<'a, bt_dht_route::Table>,
    written: &'a Notify,
}

impl Table {
    pub(crate) fn new(self_id: NodeId) -> Self {
        Self {
            table: Mutex::new(bt_dht_route::Table::new(self_id)),
            written: Notify::new(),
        }
    }

    pub(crate) fn read(&self) -> ReadGuard<'_> {
        ReadGuard {
            guard: self.table.must_lock(),
        }
    }

    pub(crate) fn write(&self) -> WriteGuard<'_> {
        WriteGuard {
            guard: self.table.must_lock(),
            written: &self.written,
        }
    }

    pub(crate) async fn written(&self) {
        self.written.notified().await
    }
}

impl Deref for ReadGuard<'_> {
    type Target = bt_dht_route::Table;

    fn deref(&self) -> &Self::Target {
        self.guard.deref()
    }
}

impl Deref for WriteGuard<'_> {
    type Target = bt_dht_route::Table;

    fn deref(&self) -> &Self::Target {
        self.guard.deref()
    }
}

impl DerefMut for WriteGuard<'_> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        self.guard.deref_mut()
    }
}

impl Drop for WriteGuard<'_> {
    fn drop(&mut self) {
        self.written.notify_waiters();
    }
}
