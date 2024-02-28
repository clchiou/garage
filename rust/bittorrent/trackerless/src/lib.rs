use std::collections::VecDeque;

use bytes::{Bytes, BytesMut};
use snafu::prelude::*;
use tokio::sync::broadcast::{error::RecvError, Receiver};

use bittorrent_base::{Features, InfoHash};
use bittorrent_bencode::serde as serde_bencode;
use bittorrent_extension::{Enabled, Handshake, Message, Metadata, PeerExchange, Reject, Request};
use bittorrent_manager::{Endpoint, Manager, Update};
use bittorrent_peer::{ExtensionMessageOwner, Peer, Recvs};

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Error {
    ExtensionChannelClosed,
    PeerUpdateChannelClosed,

    #[snafu(display("expect info_hash == {expect:?}: {info_hash:?}"))]
    ExpectInfoHash {
        info_hash: InfoHash,
        expect: InfoHash,
    },

    #[snafu(display("decode error: {source:?}"))]
    Decode {
        source: serde_bencode::Error,
    },
    #[snafu(display("extension error: {source:?}"))]
    Extension {
        source: bittorrent_extension::Error,
    },
}

#[derive(Debug)]
pub struct Trackerless<'a> {
    info_hash: InfoHash,
    self_extensions: Enabled,
    manager: &'a Manager,
    peer_update_recv: Receiver<(Endpoint, Update)>,
    recvs: &'a mut Recvs,

    info: BytesMut,
    metadata_size: Option<usize>,
    pieces: VecDeque<usize>,
    inflights: VecDeque<usize>,
}

pub type InfoOwner = bittorrent_metainfo::InfoOwner<Bytes>;

impl<'a> Trackerless<'a> {
    pub fn new(info_hash: InfoHash, manager: &'a Manager, recvs: &'a mut Recvs) -> Self {
        assert!(Features::load().extension);
        let self_extensions = Enabled::load();
        assert!(self_extensions.metadata);
        let peer_update_recv = manager.subscribe();
        Self {
            info_hash,
            self_extensions,
            manager,
            peer_update_recv,
            recvs,

            info: BytesMut::new(),
            metadata_size: None,
            pieces: VecDeque::new(),
            inflights: VecDeque::new(),
        }
    }

    pub async fn fetch(mut self) -> Result<InfoOwner, Error> {
        while !self.is_completed() {
            tokio::select! {
                update = self.peer_update_recv.recv() => {
                    self.handle_peer_update(update)?;
                }
                extension = self.recvs.extension_recv.recv() => {
                    self.handle_extension(extension)?;
                }
            }
        }
        self.finish()
    }

    //
    // Fetch State
    //

    fn is_completed(&self) -> bool {
        self.metadata_size.is_some() && self.pieces.is_empty() && self.inflights.is_empty()
    }

    fn next_piece(&mut self) -> Option<usize> {
        Some(match self.pieces.pop_front() {
            Some(piece) => {
                self.inflights.push_back(piece);
                piece
            }
            None => {
                // All piece requests have been sent out, let us re-send them in case some fail.
                // This does not seem particularly efficient, but it should suffice for now.
                let piece = self.inflights.front().copied()?;
                self.inflights.rotate_left(1);
                piece
            }
        })
    }

    fn remove_inflight(&mut self, piece: usize) -> bool {
        for (i, inflight) in self.inflights.iter().copied().enumerate() {
            if inflight == piece {
                self.inflights.swap_remove_back(i);
                return true;
            }
        }
        false
    }

    fn finish(self) -> Result<InfoOwner, Error> {
        let Self {
            info_hash: expect,
            info,
            ..
        } = self;
        let info = InfoOwner::try_from(info.freeze()).context(DecodeSnafu)?;
        let info_hash = info.deref().compute_info_hash();
        ensure!(
            info_hash == expect.as_ref(),
            ExpectInfoHashSnafu {
                info_hash: InfoHash::new(info_hash),
                expect,
            },
        );
        Ok(info)
    }

    //
    // Handlers
    //

    fn handle_peer_update(
        &mut self,
        peer_update: Result<(Endpoint, Update), RecvError>,
    ) -> Result<(), Error> {
        match peer_update {
            Ok((peer_endpoint, peer_update)) => {
                match peer_update {
                    Update::Start => {
                        let Some(peer) = self.manager.get(peer_endpoint) else {
                            return Ok(());
                        };
                        if peer.peer_features().extension {
                            self.send_handshake(&peer);
                        }
                    }
                    Update::Stop => {} // Do nothing for now.
                }
                Ok(())
            }
            Err(RecvError::Lagged(num_skipped)) => {
                tracing::warn!(num_skipped, "lag behind on peer updates");
                Ok(())
            }
            Err(RecvError::Closed) => Err(Error::PeerUpdateChannelClosed),
        }
    }

    fn handle_extension(
        &mut self,
        extension: Option<(Endpoint, ExtensionMessageOwner)>,
    ) -> Result<(), Error> {
        let (peer_endpoint, message) = extension.context(ExtensionChannelClosedSnafu)?;

        macro_rules! ensure_peer {
            ($predicate:expr, $log:expr $(,)?) => {
                if !$predicate {
                    tracing::warn!(?peer_endpoint, ?message, $log);
                    return Ok(());
                }
            };
        }

        let Some(peer) = self.manager.get(peer_endpoint) else {
            return Ok(());
        };
        ensure_peer!(
            peer.peer_features().extension,
            "peer claims non-support for extension"
        );
        match message.deref() {
            Message::Handshake(handshake) => {
                self.handle_handshake(&peer, handshake);
            }
            Message::Metadata(metadata) => {
                ensure_peer!(
                    peer.peer_extensions().metadata,
                    "peer claims non-support for metadata extension",
                );
                self.handle_metadata(&peer, metadata);
            }
            Message::PeerExchange(peer_exchange) => {
                assert!(self.self_extensions.peer_exchange);
                ensure_peer!(
                    peer.peer_extensions().peer_exchange,
                    "peer claims non-support for pex extension",
                );
                self.handle_peer_exchange(peer_exchange)?;
            }
        }
        Ok(())
    }

    fn handle_handshake(&mut self, peer: &Peer, handshake: &Handshake) {
        if self.metadata_size.is_none() {
            assert!(self.pieces.is_empty());
            let Some(metadata_size) = handshake.metadata_size else {
                return;
            };
            self.info.resize(metadata_size, 0);
            self.metadata_size = Some(metadata_size);
            self.pieces.extend(0..Metadata::num_pieces(metadata_size));

            for peer in self.manager.peers() {
                if peer.peer_features().extension && peer.peer_extensions().metadata {
                    let Some(piece) = self.next_piece() else {
                        break;
                    };
                    self.send_metadata(&peer, Metadata::Request(Request::new(piece)));
                }
            }
        } else if peer.peer_features().extension && peer.peer_extensions().metadata {
            let Some(piece) = self.next_piece() else {
                return;
            };
            self.send_metadata(peer, Metadata::Request(Request::new(piece)));
        }
    }

    fn handle_metadata(&mut self, peer: &Peer, metadata: &Metadata) {
        match metadata {
            Metadata::Request(request) => {
                self.send_metadata(peer, Metadata::Reject(Reject::new(request.piece)))
            }
            Metadata::Data(data) => {
                if self.remove_inflight(data.piece) {
                    tracing::info!(
                        peer_endpoint = ?peer.peer_endpoint(),
                        piece = data.piece,
                        "receive metadata piece",
                    );
                    self.info[Metadata::byte_range(data.piece, self.metadata_size.unwrap())]
                        .copy_from_slice(data.payload);

                    let Some(piece) = self.next_piece() else {
                        return;
                    };
                    self.send_metadata(peer, Metadata::Request(Request::new(piece)));
                }
            }
            Metadata::Reject(reject) => {
                if self.remove_inflight(reject.piece) {
                    self.pieces.push_back(reject.piece);
                }
            }
        }
    }

    fn handle_peer_exchange(&mut self, peer_exchange: &PeerExchange) -> Result<(), Error> {
        // TODO: How can we ensure that the manager is able to connect to IPv6 addresses?
        let v4 = peer_exchange.decode_added_v4().context(ExtensionSnafu)?;
        let v6 = peer_exchange.decode_added_v6().context(ExtensionSnafu)?;
        for contact_info in v4.chain(v6) {
            self.manager.connect(contact_info.endpoint, None);
        }
        Ok(())
    }

    //
    // Send Helpers
    //

    fn send_handshake(&self, peer: &Peer) {
        assert!(peer.peer_features().extension);
        // TODO: We do not have a builder API for message owners.  As a workaround, we employ an
        // encode-decode trick for now.
        let message = {
            let mut buffer = BytesMut::new();
            Handshake::new(self.metadata_size).encode(&mut buffer);
            bittorrent_extension::decode(Handshake::ID, buffer.freeze()).unwrap()
        };
        peer.send_extension(message).unwrap();
    }

    fn send_metadata(&mut self, peer: &Peer, metadata: Metadata) {
        assert!(peer.peer_features().extension);
        assert!(peer.peer_extensions().metadata);

        if let Metadata::Request(request) = &metadata {
            tracing::info!(
                peer_endpoint = ?peer.peer_endpoint(),
                piece = request.piece,
                "request metadata piece",
            );
        }

        // TODO: We do not have a builder API for message owners.  As a workaround, we employ an
        // encode-decode trick for now.
        let message = {
            let mut buffer = BytesMut::new();
            metadata.encode(&mut buffer);
            bittorrent_extension::decode(Metadata::ID, buffer.freeze()).unwrap()
        };
        peer.send_extension(message).unwrap();
    }
}
