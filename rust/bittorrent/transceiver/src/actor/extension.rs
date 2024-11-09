//! Extension Handlers

use bytes::BytesMut;

use bittorrent_extension::{Data, Error, Handshake, Message, Metadata, PeerExchange};
use bittorrent_manager::Endpoint;
use bittorrent_peer::{ExtensionMessageOwner, Peer};

use super::Actor;

impl Actor {
    #[tracing::instrument(name = "txrx/ext", fields(?peer_endpoint), skip_all)]
    pub(super) fn handle_extension(
        &mut self,
        (peer_endpoint, message): (Endpoint, ExtensionMessageOwner),
    ) {
        let Some(peer) = self.manager.get(peer_endpoint) else {
            return;
        };

        macro_rules! ensure_peer {
            ($predicate:expr, $log:expr $(,)?) => {
                if !$predicate {
                    tracing::warn!(?message, $log);
                    peer.cancel();
                    return;
                }
            };
        }

        ensure_peer!(
            peer.peer_features().extension,
            "close peer who claims non-support for extension",
        );
        match message.deref() {
            Message::Handshake(_) => {} // Nothing to do here.
            Message::Metadata(metadata) => {
                ensure_peer!(
                    peer.peer_extensions().metadata,
                    "close peer who claims non-support for metadata extension",
                );
                self.handle_metadata(&peer, metadata);
            }
            Message::PeerExchange(peer_exchange) => {
                ensure_peer!(
                    peer.peer_extensions().peer_exchange,
                    "close peer who claims non-support for pex extension",
                );
                self.handle_peer_exchange(&peer, peer_exchange);
            }
        }
    }

    fn handle_metadata(&mut self, peer: &Peer, metadata: &Metadata) {
        match metadata {
            Metadata::Request(request) => {
                let metadata_size = self.raw_info.len();

                if request.piece >= Metadata::num_pieces(metadata_size) {
                    tracing::warn!(?request, "close peer due to invalid metadata piece");
                    peer.cancel();
                    return;
                }

                let message = Metadata::Data(Data::new(
                    request.piece,
                    Some(metadata_size),
                    &self.raw_info[Metadata::byte_range(request.piece, metadata_size)],
                ))
                .to_message();
                peer.send_extension(message).unwrap();
            }
            Metadata::Data(_) | Metadata::Reject(_) => {} // Nothing to do here.
        }
    }

    fn handle_peer_exchange(&mut self, peer: &Peer, peer_exchange: &PeerExchange) {
        let result: Result<_, Error> = try {
            (
                peer_exchange.decode_added_v4()?,
                peer_exchange.decode_added_v6()?,
            )
        };
        match result {
            Ok((v4, v6)) => {
                // TODO: How can we ensure that the manager is able to connect to IPv6 addresses?
                for contact_info in v4.chain(v6) {
                    self.manager.connect(contact_info.endpoint, None);
                }
            }
            Err(error) => {
                tracing::warn!(?peer_exchange, %error, "invalid pex message");
                peer.cancel();
            }
        }
    }
}

//
// TODO: We do not have a builder API for message owners.  As a workaround, we employ an
// encode-decode trick for now.
//

pub(super) trait ToMessage {
    fn to_message(&self) -> ExtensionMessageOwner;
}

impl ToMessage for Handshake<'_> {
    fn to_message(&self) -> ExtensionMessageOwner {
        let mut buffer = BytesMut::new();
        self.encode(&mut buffer);
        bittorrent_extension::decode(Self::ID, buffer.freeze()).unwrap()
    }
}

impl ToMessage for Metadata<'_> {
    fn to_message(&self) -> ExtensionMessageOwner {
        let mut buffer = BytesMut::new();
        self.encode(&mut buffer);
        bittorrent_extension::decode(Self::ID, buffer.freeze()).unwrap()
    }
}
