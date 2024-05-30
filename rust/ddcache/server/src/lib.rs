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

use uuid::Uuid;
use zmq::{Context, ROUTER};

use g1_tokio::task::{JoinArray, JoinGuard};
use g1_zmq::Socket;

use ddcache_peer::Peer;
use ddcache_rpc::service;
use ddcache_rpc::{BlobEndpoint, Endpoint};
use ddcache_storage::Storage;

use crate::state::State;

g1_param::define!(self_id: Uuid = Uuid::new_v4());

// TODO: Add the default IPv6 address.
g1_param::define!(endpoints: Vec<String> = vec!["tcp://127.0.0.1:0".into()]);
g1_param::define!(blob_endpoints: Vec<BlobEndpoint> = vec!["127.0.0.1:0".parse().unwrap()]);

// lwm/hwm = low/high water mark
g1_param::define!(storage_size_lwm: u64 = 768 * 1024 * 1024);
g1_param::define!(storage_size_hwm: u64 = 1024 * 1024 * 1024);

g1_param::define!(max_concurrency: usize = 512);

g1_param::define!(max_key_size: usize = 128);
g1_param::define!(max_metadata_size: usize = 128);
g1_param::define!(max_blob_size: usize = 32 * 1024 * 1024);

g1_param::define!(
    blob_lease_timeout: Duration = Duration::from_secs(2);
    parse = g1_param::parse::duration;
);
g1_param::define!(
    blob_request_timeout: Duration = Duration::from_secs(8);
    parse = g1_param::parse::duration;
);

g1_param::define!(tcp_listen_backlog: u32 = 256);

#[derive(Clone, Debug)]
pub struct Server {
    endpoints: Arc<[Endpoint]>,
}

pub type ServerGuard = JoinArray<Result<(), Error>, 4>;

type Guard = JoinGuard<Result<(), Error>>;

impl Server {
    pub async fn spawn(storage_dir: &Path) -> Result<(Self, ServerGuard), Error> {
        let storage = Storage::open(storage_dir).await?;

        let self_id = *crate::self_id();
        let state = Arc::new(State::new());
        let pubsub = service::pubsub();

        let (socket, endpoints) = bind()?;
        let (blob_endpoints, blob_guard) = blob_server::Actor::spawn(state.clone())?;

        let publisher_guard = pubsub.clone().spawn(self_id, endpoints.as_slice().into());

        let (peer, mut peer_guard) = Peer::spawn(self_id, pubsub, storage.clone())
            .await
            .map_err(Error::other)?;
        let peer_guard = Guard::spawn(move |cancel| async move {
            tokio::select! {
                () = cancel.wait() => {}
                () = peer_guard.joinable() => {}
            }
            peer_guard.shutdown().await?.map_err(Error::other)
        });

        let guard = server::Actor::spawn(socket, blob_endpoints, state, storage, peer);

        Ok((
            Self {
                endpoints: endpoints.into(),
            },
            ServerGuard::new([guard, blob_guard, publisher_guard, peer_guard]),
        ))
    }

    pub fn endpoints(&self) -> &[Endpoint] {
        &self.endpoints
    }
}

fn bind() -> Result<(Socket, Vec<Endpoint>), Error> {
    let mut socket = Socket::try_from(Context::new().socket(ROUTER)?)?;
    socket.set_linger(0)?; // Do NOT block the program exit!

    let mut endpoints = Vec::with_capacity(crate::endpoints().len());
    for endpoint in crate::endpoints() {
        socket.bind(endpoint)?;
        endpoints.push(socket.get_last_endpoint().unwrap().unwrap().into());
    }
    tracing::info!(?endpoints, "bind");

    Ok((socket, endpoints))
}
