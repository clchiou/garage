#![feature(try_blocks)]
#![cfg_attr(test, feature(assert_matches))]

mod blob_server;
mod rep;
mod server;
mod state;

use std::io::Error;
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

use g1_tokio::task::{JoinArray, JoinGuard};

use ddcache_proto::{BlobEndpoint, Endpoint};

use crate::state::State;

// TODO: Add the default IPv6 address.
g1_param::define!(endpoints: Vec<String> = vec!["tcp://0.0.0.0:0".into()]);
g1_param::define!(blob_endpoints: Vec<BlobEndpoint> = vec!["0.0.0.0:0".parse().unwrap()]);

// lwm/hwm = low/high water mark
g1_param::define!(storage_size_lwm: u64 = 768 * 1024 * 1024);
g1_param::define!(storage_size_hwm: u64 = 1024 * 1024 * 1024);

g1_param::define!(max_concurrency: usize = 512);

g1_param::define!(max_key_size: usize = 128);
g1_param::define!(max_metadata_size: usize = 128);
g1_param::define!(max_blob_size: usize = 32 * 1024 * 1024);

g1_param::define!(blob_lease_timeout: Duration = Duration::from_secs(2));
g1_param::define!(blob_request_timeout: Duration = Duration::from_secs(8));

g1_param::define!(tcp_listen_backlog: u32 = 256);

#[derive(Clone, Debug)]
pub struct Server {
    endpoints: Arc<[Endpoint]>,
}

pub type ServerGuard = JoinArray<Result<(), Error>, 2>;

type Guard = JoinGuard<Result<(), Error>>;

impl Server {
    pub async fn spawn(storage_dir: &Path) -> Result<(Self, ServerGuard), Error> {
        let state = Arc::new(State::new());
        let (blob_endpoints, blob_actor_guard) = blob_server::Actor::spawn(state.clone())?;
        let (endpoints, actor_guard) =
            server::Actor::spawn(storage_dir, blob_endpoints, state).await?;
        Ok((
            Self {
                endpoints: endpoints.into(),
            },
            ServerGuard::new([actor_guard, blob_actor_guard]),
        ))
    }

    pub fn endpoints(&self) -> &[Endpoint] {
        &self.endpoints
    }
}
