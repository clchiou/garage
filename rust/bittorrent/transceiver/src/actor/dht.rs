//! DHT Handlers

use std::sync::Arc;

use bittorrent_dht::Agent;
use bittorrent_manager::Endpoint;

use super::Actor;

impl Actor {
    pub(super) fn handle_port(&mut self, (peer_endpoint, port): (Endpoint, u16)) {
        let dht = try_then!(self.dht(peer_endpoint), return);
        // We probably should not block the main loop while performing DHT pings.
        tokio::spawn(async move {
            let mut dht_endpoint = peer_endpoint;
            dht_endpoint.set_port(port);
            if let Err(error) = dht.ping(dht_endpoint).await {
                tracing::warn!(?peer_endpoint, ?port, ?error, "dht ping error");
            }
        });
    }

    pub(super) fn dht(&self, peer_endpoint: Endpoint) -> Option<Arc<Agent>> {
        if peer_endpoint.is_ipv4() {
            self.dht_ipv4.clone()
        } else {
            assert!(peer_endpoint.is_ipv6());
            self.dht_ipv6.clone()
        }
    }
}
