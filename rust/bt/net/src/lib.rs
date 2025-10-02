#![feature(type_alias_impl_trait)]

mod base;
mod connect;
mod listen;

use std::collections::HashSet;
use std::io::Error;
use std::sync::{Arc, Mutex};

use futures::future::OptionFuture;

use g1_base::sync::MutexExt;
use g1_tokio::task::{JoinGuard, JoinQueue};

use bt_base::{ConnId, Features, InfoHash, PeerEndpoint, PeerId};
use bt_model::fold::{self, Closed, Consumer, Fold, FoldGuard};
use bt_model::{Model, ModelUpdate};
use bt_peer::half_open::{HalfOpenManifold, HalfOpenMessage, HalfOpenMessageRecv};
use bt_peer::{Manifold, PeerMessage, PeerMessageRecv};

use crate::base::{HandshakeGuard, Shared};

//
// We divide connections into two groups: Connectable and non-connectable.  A connectable
// connection's peer endpoint is published on a tracker or the DHT.
//

struct NetActor {
    shared: Arc<Shared>,

    listen_tasks: JoinQueue<Result<(), Error>>,

    connects: Consumer<HashSet<(InfoHash, PeerEndpoint)>>,
    fold_guard: FoldGuard,

    peer_message_recv: PeerMessageRecv,
    half_open_message_recv: Option<HalfOpenMessageRecv>,
}

pub type NetGuard = JoinGuard<Result<(), Error>>;

struct Folder;

impl Net {
    pub fn spawn(
        self_id: PeerId,
        self_features: Features,
        model: Arc<Mutex<Model>>,
        manifold: Manifold,
        half_open: Option<HalfOpenManifold>,
    ) -> (Self, NetGuard) {
        let (connects, fold_guard) = fold::spawn(Folder, model.must_lock().subscribe());

        let peer_message_recv = manifold.subscribe();
        let half_open_message_recv = half_open.as_ref().map(HalfOpenManifold::subscribe);

        let shared = Arc::new(Shared::new(
            self_id,
            self_features,
            model,
            manifold,
            half_open,
        ));

        let actor = NetActor {
            shared,

            listen_tasks: JoinQueue::new(),

            connects,
            fold_guard,

            peer_message_recv,
            half_open_message_recv,
        };
        Self::spawn_impl(actor)
    }
}

impl Fold for Folder {
    type Value = HashSet<(InfoHash, PeerEndpoint)>;

    fn fold(&mut self, value: &mut Option<Self::Value>, update: ModelUpdate) {
        if let ModelUpdate::NewPeer(info_hash, peer_endpoint) = update {
            value
                .get_or_insert_default()
                .insert((info_hash, peer_endpoint));
        }
    }
}

#[g1_actor::actor(
    stub(
        pub, Net,
        spawn(spawn_impl),
    ),
    loop_(
        type Result<(), Error>,
        run(run_impl),
        return Ok(()),
    ),
)]
impl NetActor {
    #[actor::method(pub, stub(return {
        let result: Result<bool, Error> = match result {
            Ok(result) => result.map(|()| true),
            Err(_) => Ok(false),
        };
    }))]
    fn listen(&self, self_endpoint: PeerEndpoint) -> Result<(), Error> {
        // You typically need an address that can be published to a tracker or the DHT.
        if self_endpoint.ip().is_unspecified() {
            return Err(Error::other(format!("unspecified ip: {self_endpoint}")));
        }

        self.listen_tasks
            .push(listen::tcp::spawn(self.shared.clone(), self_endpoint)?)
            .expect("listen_tasks");

        // Connections will be made from one of these addresses (with ephemeral ports).
        self.shared.self_endpoints.must_lock().push(self_endpoint);

        Ok(())
    }

    #[actor::loop_(react = {
        let guard = self.listen_tasks.join_next();
        return Self::join_listener(guard.expect("listen_tasks"));
    })]
    fn join_listener(mut guard: JoinGuard<Result<(), Error>>) -> Result<(), Error> {
        match guard.take_result() {
            Ok(result) => result,
            Err(error) => {
                // Right now, we return `Ok`.  Should we return `Err` instead?  If so, what kind?
                tracing::warn!(%error, "listen shutdown");
                Ok(())
            }
        }
    }

    #[actor::loop_(react = {
        let guard = self.shared.handshake_tasks.join_next();
        Self::join_handshaker(guard.expect("handshake_tasks"));
    })]
    fn join_handshaker(mut guard: HandshakeGuard) {
        match guard.take_result() {
            Ok(()) => {}
            Err(error) => tracing::warn!(%error, "handshake shutdown"),
        }
    }

    #[actor::loop_(react = {
        let connects = self.connects.consume();
        match connects {
            Ok(connects) => self.consume_connects(connects),
            Err(Closed) => break,
        }
    })]
    fn consume_connects(&mut self, mut connects: HashSet<(InfoHash, PeerEndpoint)>) {
        {
            let model = self.shared.model.must_lock();
            let peers = model.peers();
            let mut conn_table = self.shared.conn_table.must_lock();
            connects.retain(|(info_hash, peer_endpoint)| {
                peers.contains(info_hash.clone(), *peer_endpoint)
                    && conn_table.connecting(info_hash.clone(), *peer_endpoint)
            });
        }

        for (info_hash, peer_endpoint) in connects {
            self.connect(info_hash, peer_endpoint);
        }
    }

    #[actor::loop_(react = {
        let message = self.peer_message_recv.recv();
        match message {
            Ok(message) => self.recv_peer_message(message),
            Err(_) => break,
        }
    })]
    fn recv_peer_message(&self, message: PeerMessage) {
        match message {
            PeerMessage::Connect(conn_id) => self.connected(conn_id),
            PeerMessage::Disconnect(conn_id, _) => self.disconnected(conn_id),
            PeerMessage::Message { .. } => {}
        }
    }

    #[actor::loop_(react = {
        let Some(message) = OptionFuture::from(
            self.half_open_message_recv
                .as_mut()
                .map(HalfOpenMessageRecv::recv),
        );
        match message {
            Ok(message) => self.recv_half_open_message(message),
            Err(_) => break,
        }
    })]
    fn recv_half_open_message(&self, message: HalfOpenMessage) {
        match message {
            HalfOpenMessage::Connect(conn_id) => self.connected(conn_id),
            HalfOpenMessage::Disconnect(conn_id, _) => self.disconnected(conn_id),
            HalfOpenMessage::Extended { .. } => {}
        }
    }

    fn connected(&self, conn_id: ConnId) {
        self.shared
            .conn_table
            .must_lock()
            .assert_connected(&conn_id);
    }

    fn disconnected(&self, conn_id: ConnId) {
        let backoff;
        {
            let mut model = self.shared.model.must_lock();
            let mut conn_table = self.shared.conn_table.must_lock();

            let Some(reconnect) = conn_table.disconnected(conn_id.clone()) else {
                return;
            };

            if !reconnect {
                let removed = model
                    .peers_mut()
                    .remove(conn_id.info_hash(), conn_id.peer_endpoint());
                if removed == Ok(true) {
                    tracing::warn!(%conn_id, "remove peer from routing table");
                }
                return;
            }

            // Check `peers().contain_torrent()` instead of `torrents().contains()` because the
            // torrents might not have been initialized yet.
            if !model.peers().contains_torrent(conn_id.info_hash()) {
                conn_table.remove_connecting(conn_id.info_hash(), conn_id.peer_endpoint());
                return;
            }

            backoff = conn_table.reconnect_backoff(conn_id.info_hash(), conn_id.peer_endpoint());
            assert!(backoff.is_some());
        }

        self.reconnect(conn_id, backoff);
    }

    async fn shutdown(&mut self, result: Result<(), Error>) -> Result<(), Error> {
        let (listen_result, handshake_result, fold_result) = tokio::join!(
            self.listen_tasks.shutdown(),
            self.shared.handshake_tasks.shutdown(),
            self.fold_guard.shutdown(),
        );

        let listen_result = match listen_result {
            Ok(result) => result,
            Err(error) => {
                // Right now, we return `Ok`.  Should we return `Err` instead?  If so, what kind?
                tracing::warn!(%error, "listen shutdown");
                Ok(())
            }
        };

        match handshake_result {
            Ok(()) => {}
            Err(error) => tracing::warn!(%error, "handshake shutdown"),
        }
        match fold_result {
            Ok(()) => {}
            Err(error) => tracing::warn!(%error, "fold shutdown"),
        }

        // The first error takes precedence over the later one.
        result.and(listen_result)
    }
}

impl NetActorLoop {
    async fn run(&mut self) -> Result<(), Error> {
        let result = self.run_impl().await;
        self.__actor.shutdown(result).await
    }
}
