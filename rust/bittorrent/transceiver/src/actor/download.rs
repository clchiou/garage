//! Download Handlers

use std::io::Error;

use bytes::Bytes;
use tokio::{sync::oneshot::error::RecvError, time::Instant};

use bittorrent_base::{BlockDesc, PieceIndex};
use bittorrent_manager::Endpoint;
use bittorrent_peer::{Full, Peer, Possession};

use super::{Actor, Update};

impl Actor {
    #[tracing::instrument(name = "txrx/down", fields(?peer_endpoint), skip_all)]
    pub(super) fn handle_possession(
        &mut self,
        (peer_endpoint, possession): (Endpoint, Possession),
    ) {
        let Some(peer) = self.manager.get(peer_endpoint) else {
            return;
        };
        if let Err(error) = self.scheduler.notify_possession(peer_endpoint, possession) {
            tracing::warn!(%error, "close peer due to invalid message");
            peer.cancel();
            return;
        }
        self.send_requests(&peer);
    }

    #[tracing::instrument(name = "txrx/down", fields(?peer_endpoint), skip_all)]
    pub(super) fn handle_suggest(&mut self, (peer_endpoint, piece): (Endpoint, PieceIndex)) {
        // For now, `handle_suggest` and `handle_allowed_fast` are the same.
        self.do_handle_allowed_fast(peer_endpoint, piece)
    }

    #[tracing::instrument(name = "txrx/down", fields(?peer_endpoint), skip_all)]
    pub(super) fn handle_allowed_fast(&mut self, (peer_endpoint, piece): (Endpoint, PieceIndex)) {
        self.do_handle_allowed_fast(peer_endpoint, piece)
    }

    fn do_handle_allowed_fast(&mut self, peer_endpoint: Endpoint, piece: PieceIndex) {
        let Some(peer) = self.manager.get(peer_endpoint) else {
            return;
        };
        let Some(piece) = self.dim.check_piece_index(piece) else {
            tracing::warn!(?piece, "close peer due to invalid piece");
            peer.cancel();
            return;
        };
        self.scheduler.assign(peer_endpoint, piece);
        self.send_requests(&peer);
    }

    #[tracing::instrument(name = "txrx/down", fields(?peer_endpoint), skip_all)]
    pub(super) async fn handle_block(
        &mut self,
        (peer_endpoint, (block, buffer)): (Endpoint, (BlockDesc, Bytes)),
    ) -> Result<(), Error> {
        // For now, we drop this block if we are not connected to this peer.  However, we accept it
        // even if we did not request it from this peer.
        let Some(peer) = self.manager.get(peer_endpoint) else {
            return Ok(());
        };
        let block = ensure_block!(self, peer, block);
        self.recv_block(peer_endpoint, block, buffer).await?;
        self.send_requests(&peer);
        Ok(())
    }

    #[tracing::instrument(name = "txrx/down", fields(?peer_endpoint), skip_all)]
    pub(super) async fn handle_response(
        &mut self,
        (peer_endpoint, request, response): (Endpoint, BlockDesc, Result<Bytes, RecvError>),
    ) -> Result<(), Error> {
        let Some(peer) = self.manager.get(peer_endpoint) else {
            return Ok(());
        };
        let request = ensure_block!(self, peer, request);
        match response {
            Ok(buffer) => self.recv_block(peer_endpoint, request, buffer).await?,
            Err(_) => {
                tracing::debug!(?request, "peer-> error");
                let piece = request.0.0;
                self.scheduler.notify_response_error(peer_endpoint, piece);
                if let Some(queue) = self.queues.get_mut(piece) {
                    queue.push_request(request);
                }
            }
        }
        self.send_requests(&peer);
        Ok(())
    }

    pub(super) fn check_endgame(&mut self) {
        if self.endgame {
            return;
        }
        if to_f64(self.scheduler.len()) > to_f64(self.dim.num_pieces) * self.endgame_threshold {
            return;
        }
        tracing::info!("enter endgame");
        self.endgame = true;
        self.scheduler
            .set_max_assignments(self.endgame_max_assignments);
        self.scheduler
            .set_max_replicates(self.endgame_max_replicates);
        self.scheduler.schedule(Instant::now());
    }

    pub(super) fn send_requests(&mut self, peer: &Peer) {
        let peer_endpoint = peer.peer_endpoint();
        let Some(assignments) = self.scheduler.assignments(peer_endpoint) else {
            return;
        };
        for piece in assignments {
            let mut queue = self.queues.get_or_default(piece);
            while let Some(request) = queue.pop_request() {
                match peer.request(request) {
                    Ok(Some(response_recv)) => {
                        tracing::debug!(?request, "->peer");
                        assert!(
                            self.responses
                                .push(async move { (peer_endpoint, request, response_recv.await) })
                                .is_ok()
                        );
                    }
                    Ok(None) => {} // We already sent the request to this peer.
                    Err(Full) => {
                        queue.push_request(request);
                        break;
                    }
                }
            }
        }
    }

    // NOTE: This method assumes the caller has checked `block`.
    async fn recv_block(
        &mut self,
        peer_endpoint: Endpoint,
        block: BlockDesc,
        mut buffer: Bytes,
    ) -> Result<(), Error> {
        tracing::debug!(?block, "peer->");
        let piece = block.0.0;

        // Skip this block if we already have it.
        if self.self_pieces[usize::from(piece)] {
            return Ok(());
        }
        let mut queue = self.queues.get_or_default(piece);
        if queue.add_progress(peer_endpoint, block) == 0 {
            return Ok(());
        }

        self.storage.write(block, &mut buffer).await?;

        if !queue.is_completed() {
            return Ok(());
        }
        let recv_stats = queue.remove();

        if !self.storage.verify(piece).await? {
            tracing::warn!(?piece, ?recv_stats, "verification fail");
            return Ok(());
        }

        tracing::info!(?piece, ?recv_stats, "download");
        self.self_pieces.set(usize::from(piece), true);

        let mut total = 0;
        for (p, n) in recv_stats {
            self.stats.get_mut(p).recv += n;
            total += n;
        }
        self.torrent.recv.add(total);
        self.torrent.have.add(self.dim.piece_size(piece));

        self.scheduler.notify_verified(piece);
        self.check_endgame();

        let _ = self.update_send.send(Update::Download(piece));
        for peer in self.manager.peers() {
            peer.possess(Possession::Have(piece)).unwrap();
        }

        Ok(())
    }
}

fn to_f64(x: usize) -> f64 {
    u32::try_from(x).unwrap().into()
}
