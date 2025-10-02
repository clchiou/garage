pub(crate) mod tcp;

use std::sync::Arc;

use g1_base::sync::MutexExt;
use g1_tokio::task::Cancel;

use bt_base::{ConnId, PeerEndpoint};

use crate::base::{HandshakeGuard, RawConn, Shared};

struct AcceptActor {
    shared: Arc<Shared>,
    self_endpoint: PeerEndpoint,
    peer_endpoint: PeerEndpoint,
}

fn spawn(
    shared: Arc<Shared>,
    self_endpoint: PeerEndpoint,
    peer_endpoint: PeerEndpoint,
    raw_conn: RawConn,
) -> HandshakeGuard {
    let actor = AcceptActor {
        shared,
        self_endpoint,
        peer_endpoint,
    };
    HandshakeGuard::spawn(move |cancel| actor.run(cancel, raw_conn))
}

impl AcceptActor {
    async fn run(self, cancel: Cancel, raw_conn: RawConn) {
        tokio::select! {
            () = cancel.wait() => (),
            () = self.accept(raw_conn) => (),
        }
    }

    async fn accept(&self, mut raw_conn: RawConn) {
        let (info_hash, peer_id, peer_features) =
            match self.shared.handshaker.accept(raw_conn.raw_conn()).await {
                Ok(tuple) => tuple,
                Err(error) => {
                    tracing::warn!(
                        self_endpoint = %self.self_endpoint,
                        peer_endpoint = %self.peer_endpoint,
                        proto = ?raw_conn.proto(),
                        %error,
                        "accept",
                    );
                    return;
                }
            };

        let conn_id = ConnId::from((info_hash, self.self_endpoint, self.peer_endpoint));
        tracing::debug!(%conn_id, proto = ?raw_conn.proto(), %peer_id, "accept");

        // If a peer uses uTP, its connections are most likely initiated from a connectable
        // endpoint.
        let inserted = if self
            .shared
            .model
            .must_lock()
            .peers()
            .contains(conn_id.info_hash(), conn_id.peer_endpoint())
        {
            self.shared
                .conn_table
                .must_lock()
                .connected(conn_id.clone(), raw_conn.proto())
        } else {
            false
        };

        self.shared
            .spawn(conn_id.clone(), peer_features, raw_conn, inserted)
            .await;
    }
}
