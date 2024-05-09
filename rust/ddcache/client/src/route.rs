use std::collections::{hash_map::Entry, HashMap};
use std::io;

use snafu::prelude::*;
use tokio::task::Id;

use g1_base::iter::IteratorExt;
use g1_tokio::task::JoinQueue;

use ddcache_client_raw::RawClient;
use ddcache_rpc::service;
use ddcache_rpc::Endpoint;

use crate::error::{DisconnectedSnafu, Error, NotConnectedSnafu, ProtocolSnafu};

#[derive(Debug)]
pub(crate) struct RouteMap {
    shards: HashMap<Endpoint, RawClient>,
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
                let (shard, guard) = RawClient::connect(endpoint.clone()).context(ProtocolSnafu)?;
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

    pub(crate) fn get(&self, endpoint: Endpoint) -> Result<RawClient, Error> {
        self.shards
            .get(&endpoint)
            .cloned()
            .context(DisconnectedSnafu { endpoint })
    }

    pub(crate) fn all(&self) -> Result<Vec<RawClient>, Error> {
        let shards: Vec<_> = self.shards.values().cloned().collect();
        ensure!(!shards.is_empty(), NotConnectedSnafu);
        Ok(shards)
    }

    /// Finds shards via the Rendezvous Hashing algorithm.
    pub(crate) fn find(&self, key: &[u8], num_replicas: usize) -> Result<Vec<RawClient>, Error> {
        let mut shards =
            self.shards.values().cloned().collect_then_sort_by_key(
                service::rendezvous_sorting_by_key(key, RawClient::endpoint),
            );
        ensure!(!shards.is_empty(), NotConnectedSnafu);
        shards.truncate(num_replicas);
        Ok(shards)
    }

    pub(crate) fn remove(&mut self, id: Id) -> Option<RawClient> {
        let endpoint = self.endpoints.remove(&id)?;
        Some(self.shards.remove(&endpoint).unwrap())
    }
}
