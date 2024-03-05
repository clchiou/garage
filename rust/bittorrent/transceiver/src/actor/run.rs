//! Actor Runner

use std::cmp;
use std::io::Error;
use std::time::Duration;

use tokio::{
    sync::broadcast::error::RecvError,
    time::{self, Instant},
};

use bittorrent_manager::Update as PeerUpdate;

use super::{Actor, Update};

impl Actor {
    pub(crate) async fn run(mut self) -> Result<(), Error> {
        // Should we parameterize this?
        const IDLE_TIMEOUT: Duration = Duration::from_secs(60);

        self.check_endgame();

        for peer in self.manager.peers() {
            self.handle_peer_update((peer.peer_endpoint(), PeerUpdate::Start));
        }

        let seed_at_start = self.scheduler.is_completed();
        let mut was_idle = true;
        let _ = self.update_send.send(Update::Start);
        loop {
            // TODO: Implement seeding.
            if self.scheduler.is_completed() {
                tracing::info!("download completed");
                // BEP 3 specifies that we should not send `Update::Complete` if we were a seed at
                // the start.
                if !seed_at_start {
                    let _ = self.update_send.send(Update::Complete);
                }
                break;
            }

            tokio::select! {
                () = self.cancel.wait() => break,

                message = self.peer_update_recv.recv() => {
                    match message {
                        Ok(message) => self.handle_peer_update(message),
                        Err(RecvError::Lagged(num_skipped)) => {
                            // TODO: Should we return an error instead?
                            tracing::warn!(num_skipped, "lag behind on peer updates");
                        }
                        Err(RecvError::Closed) => break,
                    }
                }

                message = self.recvs.port_recv.recv() => {
                    let Some(message) = message else { break };
                    self.handle_port(message);
                }

                message = self.recvs.extension_recv.recv() => {
                    let Some(message) = message else { break };
                    self.handle_extension(message);
                }

                //
                // Upload
                //

                message = self.recvs.interested_recv.recv() => {
                    let Some(message) = message else { break };
                    self.handle_interested(message);
                }
                message = self.recvs.request_recv.recv() => {
                    let Some(message) = message else { break };
                    self.handle_request(message).await?;
                }

                //
                // Download
                //

                message = self.recvs.possession_recv.recv() => {
                    let Some(message) = message else { break };
                    self.handle_possession(message);
                }
                message = self.recvs.suggest_recv.recv() => {
                    let Some(message) = message else { break };
                    self.handle_suggest(message);
                }
                message = self.recvs.allowed_fast_recv.recv() => {
                    let Some(message) = message else { break };
                    self.handle_allowed_fast(message);
                }
                message = self.recvs.block_recv.recv() => {
                    let Some(message) = message else { break };
                    self.handle_block(message).await?;
                }

                message = self.responses.pop_ready() => {
                    // We can call `unwrap` because `responses` is never closed.
                    self.handle_response(message.unwrap()).await?;
                }

                () = {
                    let now = Instant::now();
                    let idle_deadline = now + IDLE_TIMEOUT;
                    let deadline = cmp::min(
                        self.scheduler.next_backoff(now).unwrap_or(idle_deadline),
                        idle_deadline,
                    );
                    time::sleep_until(deadline)
                } => {}
            }

            self.scheduler.remove_expired_backoffs(Instant::now());

            for peer_endpoint in self.scheduler.take_updated() {
                if let Some(peer) = self.manager.get(peer_endpoint) {
                    self.send_requests(&peer);
                }
            }

            if self.scheduler.is_idle() {
                if !was_idle {
                    tracing::info!("download becomes idle");
                    let _ = self.update_send.send(Update::Idle);
                }
                was_idle = true;
            } else {
                was_idle = false;
            }
        }
        let _ = self.update_send.send(Update::Stop);

        Ok(())
    }
}
