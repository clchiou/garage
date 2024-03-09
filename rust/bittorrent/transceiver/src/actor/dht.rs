//! DHT Handlers

use std::io::ErrorKind;

use bittorrent_dht::Dht;
use bittorrent_manager::Endpoint;

use super::Actor;

impl Actor {
    #[tracing::instrument(name = "txrx/dht", skip(self))]
    pub(super) fn handle_port(&mut self, (peer_endpoint, port): (Endpoint, u16)) {
        if let Some(dht) = self.dht(peer_endpoint) {
            // We probably should not block the main loop while performing DHT pings.
            tokio::spawn(Self::dht_ping(dht, peer_endpoint, port));
        };
    }

    #[tracing::instrument(name = "txrx/dht", skip(dht))]
    async fn dht_ping(dht: Dht, peer_endpoint: Endpoint, port: u16) {
        let mut dht_endpoint = peer_endpoint;
        dht_endpoint.set_port(port);
        if let Err(error) = dht.ping(dht_endpoint).await {
            if error.kind() == ErrorKind::TimedOut {
                tracing::debug!(?error, "dht ping timeout");
            } else {
                tracing::warn!(?error, "dht ping error");
            }
        }
    }

    pub(super) fn dht(&self, peer_endpoint: Endpoint) -> Option<Dht> {
        if peer_endpoint.is_ipv4() {
            self.dht_ipv4.clone()
        } else {
            assert!(peer_endpoint.is_ipv6());
            self.dht_ipv6.clone()
        }
    }
}
