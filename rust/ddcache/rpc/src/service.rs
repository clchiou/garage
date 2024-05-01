use std::sync::Arc;

use serde::{Deserialize, Serialize};

use etcd_client::Client;

use crate::Endpoint;

pub const PREFIX: &str = "/ddcache/service/";

pub type PubSub = etcd_pubsub::PubSub<Service, Arc<Client>>;
pub type Subscriber = etcd_pubsub::Subscriber<Service>;
pub type Event = etcd_pubsub::Event<Service>;
pub type Item = etcd_pubsub::Item<Service>;

pub fn pubsub() -> PubSub {
    PubSub::with_client(PREFIX.to_string(), Arc::new(Client::new()))
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct Service {
    pub endpoints: Vec<String>,
}

impl<'a> From<&'a [Endpoint]> for Service {
    fn from(endpoints: &'a [Endpoint]) -> Self {
        Self {
            endpoints: endpoints.iter().map(|e| e.to_string()).collect(),
        }
    }
}
