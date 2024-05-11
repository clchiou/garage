use std::collections::{hash_map::Entry, HashMap};
use std::io;

use snafu::prelude::*;
use tokio::task::Id;
use uuid::Uuid;

use g1_base::iter::IteratorExt;
use g1_tokio::task::JoinQueue;

use ddcache_client_raw::RawClient;
use ddcache_rpc::service::{self, Server};

use crate::error::{Error, NotConnectedSnafu};

#[derive(Debug)]
pub(crate) struct RouteMap {
    shards: HashMap<Uuid, RawClient>,
    ids: HashMap<Id, Uuid>,
}

impl RouteMap {
    pub(crate) fn new() -> Self {
        Self {
            shards: HashMap::new(),
            ids: HashMap::new(),
        }
    }

    pub(crate) fn connect(
        &mut self,
        tasks: &JoinQueue<Result<(), io::Error>>,
        id: Uuid,
        server: Server,
    ) {
        match self.shards.entry(id) {
            Entry::Occupied(entry) => entry.get().update(server),
            Entry::Vacant(entry) => {
                let (shard, guard) = RawClient::connect(id, server);
                assert!(self.ids.insert(guard.id(), id).is_none());
                tasks.push(guard).unwrap();
                entry.insert(shard);
            }
        }
    }

    pub(crate) fn disconnect(&self, id: Uuid) {
        if let Some(shard) = self.shards.get(&id) {
            shard.disconnect();
        }
    }

    fn iter(&self) -> impl Iterator<Item = (Uuid, RawClient)> + '_ {
        self.shards.iter().map(|(k, v)| (*k, v.clone()))
    }

    pub(crate) fn all(&self) -> Result<Vec<(Uuid, RawClient)>, Error> {
        let shards: Vec<_> = self.iter().collect();
        ensure!(!shards.is_empty(), NotConnectedSnafu);
        Ok(shards)
    }

    /// Finds shards via the Rendezvous Hashing algorithm.
    pub(crate) fn find(
        &self,
        key: &[u8],
        num_replicas: usize,
    ) -> Result<Vec<(Uuid, RawClient)>, Error> {
        let mut shards = self
            .iter()
            .collect_then_sort_by_key(service::rendezvous_sorting_by_key(key, |(id, _)| *id));
        ensure!(!shards.is_empty(), NotConnectedSnafu);
        shards.truncate(num_replicas);
        Ok(shards)
    }

    pub(crate) fn remove(&mut self, task_id: Id) -> Option<(Uuid, RawClient)> {
        let id = self.ids.remove(&task_id)?;
        Some((id, self.shards.remove(&id).unwrap()))
    }
}
