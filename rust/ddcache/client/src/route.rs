use std::collections::{hash_map::Entry, HashMap};
use std::hash::Hasher;
use std::io;

use fasthash::{CityHasher, FastHasher};
use snafu::prelude::*;
use tokio::task::Id;

use g1_base::iter::IteratorExt;
use g1_tokio::task::JoinQueue;

use ddcache_proto::Endpoint;

use crate::error::{DisconnectedSnafu, Error, NotConnectedSnafu};
use crate::shard::Shard;

#[derive(Debug)]
pub(crate) struct RouteMap {
    shards: HashMap<Endpoint, Shard>,
    endpoints: HashMap<Id, Endpoint>,
}

impl RouteMap {
    pub(crate) fn new() -> Self {
        Self {
            shards: HashMap::new(),
            endpoints: HashMap::new(),
        }
    }

    pub(crate) fn connect(
        &mut self,
        tasks: &JoinQueue<Result<(), io::Error>>,
        endpoint: Endpoint,
    ) -> Result<(), Error> {
        match self.shards.entry(endpoint.clone()) {
            Entry::Occupied(_) => tracing::debug!(%endpoint, "already connected"),
            Entry::Vacant(entry) => {
                let (shard, guard) = Shard::connect(endpoint.clone())?;
                assert!(self.endpoints.insert(guard.id(), endpoint).is_none());
                tasks.push(guard).unwrap();
                entry.insert(shard);
            }
        }
        Ok(())
    }

    pub(crate) fn disconnect(&self, endpoint: Endpoint) {
        if let Some(shard) = self.shards.get(&endpoint) {
            shard.disconnect();
        }
    }

    pub(crate) fn get(&self, endpoint: Endpoint) -> Result<Shard, Error> {
        self.shards
            .get(&endpoint)
            .cloned()
            .context(DisconnectedSnafu { endpoint })
    }

    /// Finds shards via the Rendezvous Hashing algorithm.
    pub(crate) fn find(&self, key: &[u8], num_replicas: usize) -> Result<Vec<Shard>, Error> {
        let mut shards = self
            .shards
            .values()
            .cloned()
            .collect_then_sort_by_key(|shard| {
                // Invert bits so that the vector is sorted in descending order.
                !rendezvous_hash(key, shard)
            });
        ensure!(!shards.is_empty(), NotConnectedSnafu);
        shards.truncate(num_replicas);
        Ok(shards)
    }

    pub(crate) fn remove(&mut self, id: Id) -> Option<Shard> {
        let endpoint = self.endpoints.remove(&id)?;
        Some(self.shards.remove(&endpoint).unwrap())
    }
}

fn rendezvous_hash(key: &[u8], shard: &Shard) -> u64 {
    let mut hasher = CityHasher::new();
    hasher.write(key);
    hasher.write(shard.endpoint().as_bytes());
    hasher.finish()
}
