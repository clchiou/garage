//! Upload Handlers

use std::io::Error;

use bytes::BytesMut;

use bittorrent_base::{BlockDesc, BlockOffset};
use bittorrent_manager::Endpoint;
use bittorrent_peer::ResponseSend;

use super::Actor;

impl Actor {
    pub(super) fn handle_interested(&self, peer: Endpoint) {
        try_then!(self.manager.get(peer), return).set_self_choking(self.should_choke_peer(peer, 0));
    }

    pub(super) async fn handle_request(
        &mut self,
        (peer_endpoint, block, response_send): (Endpoint, BlockDesc, ResponseSend),
    ) -> Result<(), Error> {
        let peer = try_then!(self.manager.get(peer_endpoint), return Ok(()));
        let block = ensure_block!(self, peer, block);

        let BlockDesc(BlockOffset(piece, _), size) = block;
        if !self.self_pieces[usize::from(piece)] {
            return Ok(());
        }
        if self.should_choke_peer(peer_endpoint, size) {
            peer.set_self_choking(true);
            return Ok(());
        }

        tracing::debug!(?peer_endpoint, ?block, "->peer");
        let mut buffer = BytesMut::with_capacity(size.try_into().unwrap());
        self.storage.read(block, &mut buffer).await?;
        let _ = response_send.send(buffer.freeze());

        self.stats.get_mut(peer_endpoint).send += size;
        self.torrent.send.add(size);

        Ok(())
    }

    fn should_choke_peer(&self, peer: Endpoint, request_size: u64) -> bool {
        let stat = self.stats.get(peer);
        stat.send + request_size > stat.recv + self.reciprocate_margin
    }
}
