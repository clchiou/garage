mod tcp;

use std::net::Ipv4Addr;
use std::sync::Arc;
use std::time::Duration;

use tokio::time;

use g1_base::sync::MutexExt;
use g1_tokio::task::Cancel;

use bt_base::{ConnId, Features, InfoHash, PeerEndpoint};

use crate::NetActor;
use crate::base::{HandshakeGuard, RawConn, Shared};

struct ConnectActor {
    shared: Arc<Shared>,
    info_hash: InfoHash,
    self_endpoints: Vec<PeerEndpoint>,
    peer_endpoint: PeerEndpoint,
    backoff: Option<Duration>,
}

impl NetActor {
    // NOTE: The caller must ensure that `conn_table` entry is present and `!is_connected()`.
    pub(crate) fn connect(&self, info_hash: InfoHash, peer_endpoint: PeerEndpoint) {
        self.spawn_connect(info_hash, None, peer_endpoint, None);
    }

    // NOTE: The caller must ensure that `conn_table` entry is present and `!is_connected()`.
    pub(crate) fn reconnect(&self, conn_id: ConnId, backoff: Option<Duration>) {
        self.spawn_connect(
            conn_id.info_hash(),
            Some(conn_id.self_endpoint()),
            conn_id.peer_endpoint(),
            backoff,
        );
    }

    fn spawn_connect(
        &self,
        info_hash: InfoHash,
        self_endpoint: Option<PeerEndpoint>,
        peer_endpoint: PeerEndpoint,
        backoff: Option<Duration>,
    ) {
        let mut self_endpoints = Vec::new();
        let addr = self_endpoint.map(|self_endpoint| self_endpoint.ip());
        for mut self_endpoint in self
            .shared
            .self_endpoints
            .must_lock()
            .iter()
            .copied()
            .chain([
                // TODO: Support IPv6.
                (Ipv4Addr::UNSPECIFIED, 0).into(),
            ])
        {
            // TODO: Should we use a fixed set of local ports instead of ephemeral ones?
            self_endpoint.set_port(0);
            if !self_endpoints.contains(&self_endpoint) {
                if Some(self_endpoint.ip()) == addr {
                    self_endpoints.insert(0, self_endpoint);
                } else {
                    self_endpoints.push(self_endpoint);
                }
            }
        }

        let actor = ConnectActor {
            shared: self.shared.clone(),
            info_hash,
            self_endpoints,
            peer_endpoint,
            backoff,
        };
        self.shared
            .handshake_tasks
            .push(HandshakeGuard::spawn(move |cancel| actor.run(cancel)))
            .expect("handshake_tasks");
    }
}

impl ConnectActor {
    async fn run(mut self, cancel: Cancel) {
        tokio::select! {
            () = cancel.wait() => (),
            () = self.connect() => (),
        }
    }

    fn conn_id(&self, self_endpoint: PeerEndpoint) -> ConnId {
        (self.info_hash.clone(), self_endpoint, self.peer_endpoint).into()
    }

    async fn connect(&mut self) {
        let (conn_id, peer_features, raw_conn) = loop {
            if let Some(backoff) = self.backoff {
                time::sleep(backoff).await;
            }

            if let Some(tuple) = self.try_connect().await {
                break tuple;
            }

            if !self.disconnected() {
                return;
            }
        };

        self.shared
            .conn_table
            .must_lock()
            .connecting_connected(conn_id.clone(), raw_conn.proto());

        self.shared
            .spawn(conn_id, peer_features, raw_conn, true)
            .await;
    }

    async fn try_connect(&self) -> Option<(ConnId, Features, RawConn)> {
        let mut connected = None;
        assert!(!self.self_endpoints.is_empty());
        for self_endpoint in &self.self_endpoints {
            if let Some((self_endpoint, raw_conn)) = self.try_connect_one(*self_endpoint).await {
                connected = Some((self.conn_id(self_endpoint), raw_conn));
                break;
            }
        }
        let (conn_id, mut raw_conn) = connected?;

        let (peer_id, peer_features) = self
            .shared
            .handshaker
            .connect(raw_conn.raw_conn(), conn_id.info_hash())
            .await
            .inspect_err(|error| tracing::warn!(%conn_id, %error, "connect"))
            .ok()?;

        tracing::debug!(%conn_id, proto = ?raw_conn.proto(), %peer_id, "connect");

        Some((conn_id, peer_features, raw_conn))
    }

    async fn try_connect_one(
        &self,
        self_endpoint: PeerEndpoint,
    ) -> Option<(PeerEndpoint, RawConn)> {
        tcp::connect(self_endpoint, self.peer_endpoint)
            .await
            .inspect_err(|error| {
                let conn_id = self.conn_id(self_endpoint);
                tracing::warn!(%conn_id, %error, "connect");
            })
            .ok()
    }

    // TODO: Refactor this with `NetActor::disconnected()`.
    fn disconnected(&mut self) -> bool {
        let mut model = self.shared.model.must_lock();
        let mut conn_table = self.shared.conn_table.must_lock();

        let reconnect =
            conn_table.connecting_disconnected(self.info_hash.clone(), self.peer_endpoint);

        if !reconnect {
            let info_hash = &self.info_hash;
            let peer_endpoint = self.peer_endpoint;
            if model.peers_mut().remove(info_hash.clone(), peer_endpoint) == Ok(true) {
                tracing::warn!(%info_hash, %peer_endpoint, "remove peer from routing table");
            }
            return false;
        }

        // Check `peers().contain_torrent()` instead of `torrents().contains()` because the
        // torrents might not have been initialized yet.
        if !model.peers().contains_torrent(self.info_hash.clone()) {
            conn_table.remove_connecting(self.info_hash.clone(), self.peer_endpoint);
            return false;
        }

        self.backoff = conn_table.reconnect_backoff(self.info_hash.clone(), self.peer_endpoint);
        assert!(self.backoff.is_some());

        true
    }
}
