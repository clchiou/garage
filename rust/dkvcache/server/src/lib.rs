#![feature(try_blocks)]

mod server;

use std::io::Error;
use std::path::Path;
use std::sync::Arc;

use uuid::Uuid;
use zmq::{Context, ROUTER};

use g1_tokio::task::{JoinArray, JoinGuard};
use g1_zmq::Socket;

use dkvcache_peer::Peer;
use dkvcache_rpc::Endpoint;
use dkvcache_rpc::service;
use dkvcache_storage::Storage;

use crate::server::Actor;

g1_param::define!(self_id: Uuid = Uuid::new_v4());

// TODO: Add the default IPv6 address.
g1_param::define!(endpoints: Vec<String> = vec!["tcp://127.0.0.1:0".into()]);

// lwm/hwm = low/high water mark
g1_param::define!(storage_len_lwm: usize = 768 * 1024);
g1_param::define!(storage_len_hwm: usize = 1024 * 1024);

g1_param::define!(max_concurrency: usize = 512);

g1_param::define!(max_key_size: usize = 128);
g1_param::define!(max_value_size: usize = 1024);

#[derive(Clone, Debug)]
pub struct Server {
    endpoints: Arc<[Endpoint]>,
}

pub type ServerGuard = JoinArray<Result<(), Error>, 3>;

type Guard = JoinGuard<Result<(), Error>>;

impl Server {
    pub async fn spawn(storage_path: &Path) -> Result<(Self, ServerGuard), Error> {
        let storage = Storage::open(storage_path).map_err(Error::other)?;

        let self_id = *crate::self_id();
        let pubsub = service::pubsub();

        let (socket, endpoints) = bind()?;

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

        let guard = Actor::spawn(socket, storage, peer);

        Ok((
            Self {
                endpoints: endpoints.into(),
            },
            ServerGuard::new([guard, publisher_guard, peer_guard]),
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
