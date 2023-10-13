use std::io::{Error, ErrorKind};
use std::net::SocketAddr;
use std::sync::Arc;

use bytes::Bytes;
use futures::{sink::Sink, stream::Stream};
use tokio::{sync::Mutex, task::JoinHandle};

use g1_tokio::task::{self, JoinTaskError};

use bittorrent_base::InfoHash;

use crate::{
    lookup::{Lookup, LookupPeers},
    reqrep::{self, GetPeers, Nodes},
    server::{Inner, Server},
    NodeId,
};

#[derive(Debug)]
pub struct Agent {
    self_endpoint: SocketAddr,
    inner: Arc<Inner>,
    task: Mutex<JoinHandle<Result<(), Error>>>,
}

impl Agent {
    pub fn new_default<Incoming, Outgoing>(
        self_endpoint: SocketAddr,
        incoming: Incoming,
        outgoing: Outgoing,
    ) -> Self
    where
        Incoming: Stream<Item = Result<(SocketAddr, Bytes), Error>> + Send + Unpin + 'static,
        Outgoing: Sink<(SocketAddr, Bytes), Error = Error> + Send + Unpin + 'static,
    {
        let self_id = crate::self_id().clone();
        tracing::info!(?self_id);
        let server = Server::new(self_id, reqrep::new(incoming, outgoing));
        let inner = server.inner();
        Self {
            self_endpoint,
            inner,
            task: Mutex::new(tokio::spawn(server.run())),
        }
    }

    pub fn self_id(&self) -> NodeId {
        self.inner.self_id.clone()
    }

    pub fn self_endpoint(&self) -> SocketAddr {
        self.self_endpoint
    }

    pub async fn ping(&self, peer_endpoint: SocketAddr) -> Result<(), Error> {
        self.inner.connect(peer_endpoint).ping().await
    }

    pub async fn find_node(
        &self,
        peer_endpoint: SocketAddr,
        target: &[u8],
    ) -> Result<Nodes, Error> {
        self.inner.connect(peer_endpoint).find_node(target).await
    }

    pub async fn get_peers(
        &self,
        peer_endpoint: SocketAddr,
        info_hash: &[u8],
    ) -> Result<GetPeers, Error> {
        self.inner.connect(peer_endpoint).get_peers(info_hash).await
    }

    pub async fn announce_peer(
        &self,
        peer_endpoint: SocketAddr,
        info_hash: &[u8],
        port: u16,
        implied_port: Option<bool>,
        token: &[u8],
    ) -> Result<(), Error> {
        self.inner
            .connect(peer_endpoint)
            .announce_peer(info_hash, port, implied_port, token)
            .await
    }

    pub async fn lookup_nodes(&self, id: NodeId) -> Nodes {
        Lookup::new(self.inner.clone()).lookup_nodes(id).await
    }

    pub async fn lookup_peers(&self, info_hash: InfoHash) -> LookupPeers {
        Lookup::new(self.inner.clone())
            .lookup_peers(info_hash)
            .await
    }

    pub fn close(&self) {
        self.inner.reqrep.close();
    }

    pub async fn shutdown(&self) -> Result<(), Error> {
        self.close();
        task::join_task(&self.task, *crate::grace_period())
            .await
            .map_err(|error| match error {
                JoinTaskError::Cancelled => Error::other("dht server is cancelled"),
                JoinTaskError::Timeout => Error::new(
                    ErrorKind::TimedOut,
                    "dht server shutdown grace period is exceeded",
                ),
            })?
    }
}

impl Drop for Agent {
    fn drop(&mut self) {
        self.task.get_mut().abort();
    }
}
