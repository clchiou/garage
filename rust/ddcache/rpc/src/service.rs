use std::cmp::Reverse;
use std::hash::Hasher;
use std::sync::Arc;

use fasthash::{CityHasher, FastHasher};
use serde::{Deserialize, Serialize};

use etcd_client::Client;

use crate::Endpoint;

pub const PREFIX: &str = "/ddcache/server/";

pub type PubSub = etcd_pubsub::PubSub<Server, Arc<Client>>;
pub type Subscriber = etcd_pubsub::Subscriber<Server>;
pub type Event = etcd_pubsub::Event<Server>;
pub type Item = etcd_pubsub::Item<Server>;

pub fn pubsub() -> PubSub {
    PubSub::with_client(PREFIX.to_string(), Arc::new(Client::new()))
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct Server {
    pub endpoints: Vec<String>,
}

impl<'a> From<&'a [Endpoint]> for Server {
    fn from(endpoints: &'a [Endpoint]) -> Self {
        Self {
            endpoints: endpoints.iter().map(|e| e.to_string()).collect(),
        }
    }
}

// Sort in descending order.
pub fn rendezvous_sorting_by_key<'a, T>(
    key: &'a [u8],
    mut endpoint: impl FnMut(&T) -> Endpoint + 'a,
) -> impl FnMut(&T) -> Reverse<u64> + 'a {
    move |server| Reverse(rendezvous_hash(key, endpoint(server)))
}

pub fn rendezvous_hash(key: &[u8], endpoint: Endpoint) -> u64 {
    let mut hasher = CityHasher::new();
    hasher.write(key);
    hasher.write(endpoint.as_bytes());
    hasher.finish()
}
