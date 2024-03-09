//! Peer Handlers

use bytes::Bytes;

use bittorrent_extension::Handshake;
use bittorrent_manager::{Endpoint, Update};
use bittorrent_peer::{Peer, Possession};

use super::{extension::ToMessage, Actor};

impl Actor {
    #[tracing::instrument(name = "txrx/peer", skip(self))]
    pub(super) fn handle_peer_update(&mut self, (peer_endpoint, update): (Endpoint, Update)) {
        match update {
            Update::Start => {
                let Some(peer) = self.manager.get(peer_endpoint) else {
                    return;
                };
                self.send_handshake(&peer);
            }
            Update::Stop => {
                self.queues.remove_peer(peer_endpoint);
            }
        }
        self.scheduler.notify_peer_update(peer_endpoint, update);
    }

    fn send_handshake(&self, peer: &Peer) {
        let peer_features = peer.peer_features();

        let possession = if self.self_features.fast && peer_features.fast {
            if self.self_pieces.all() {
                Some(Possession::HaveAll)
            } else if self.self_pieces.not_any() {
                Some(Possession::HaveNone)
            } else {
                None
            }
        } else {
            None
        };
        let possession = possession.unwrap_or_else(|| {
            Possession::Bitfield(Bytes::copy_from_slice(self.self_pieces.as_raw_slice()))
        });
        peer.possess(possession).unwrap();

        if self.self_features.dht && peer_features.dht {
            if let Some(self_endpoint) = self
                .dht(peer.peer_endpoint())
                .map(|dht| dht.self_endpoint())
            {
                peer.send_port(self_endpoint.port()).unwrap();
            }
        }

        if self.self_features.extension && peer_features.extension {
            let message = Handshake::new(Some(self.raw_info.len())).to_message();
            peer.send_extension(message).unwrap();
        }
    }
}
