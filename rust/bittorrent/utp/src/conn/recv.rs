use std::sync::Mutex;

use bytes::Bytes;
use futures::future::OptionFuture;
use tokio::time::{self, Instant};

use g1_base::sync::MutexExt;

use crate::packet::{Packet, PacketType};
use crate::timestamp::Timestamp;

use super::{actor::Actor, state::State, Error, IncomingRecv};

#[derive(Debug)]
struct RecvState {
    grace_period: Option<Instant>,
    // libutp seems to expect an ack for the finish packet; otherwise, it keeps resending the
    // finish packet.
    fin_ack_sent: bool,
}

impl Actor<Mutex<State>> {
    pub(super) async fn recv(&self, mut incoming_recv: IncomingRecv) -> Result<(), Error> {
        let mut recv_state = RecvState {
            grace_period: None,
            fin_ack_sent: false,
        };

        while !self.is_completed() {
            let (packet, recv_at) = match self
                .recv_packet(&mut incoming_recv, recv_state.grace_period)
                .await?
            {
                Some(incoming) => incoming,
                None => break,
            };

            let packet_type = packet.header.packet_type();
            if packet_type == PacketType::Reset {
                tracing::debug!(seq = packet.header.seq, "receive reset");
                if self.is_completed() {
                    break;
                } else {
                    return Err(Error::ConnectionReset);
                }
            }
            if packet_type == PacketType::Synchronize {
                return Err(Error::UnexpectedResynchronize);
            }

            let (packets, payloads) = self.handle_packet(&mut recv_state, packet, recv_at)?;

            for packet in packets {
                self.outgoing_send(packet).await?;
            }
            for payload in payloads {
                if !self.stream_incoming_send(payload).await? {
                    tracing::debug!("drop payloads because utp recv stream was dropped");
                    break;
                }
            }
        }
        if self.state.must_lock().recv_window.is_completed() {
            assert!(recv_state.fin_ack_sent);
        }

        tracing::debug!("utp connection actor receive-half is completed");
        Ok(())
    }

    fn is_completed(&self) -> bool {
        let state = self.state.must_lock();
        state.send_window.is_completed()
            && (state.recv_window.is_completed() || self.stream_incoming_is_closed())
    }

    fn is_only_recv_not_completed(&self) -> bool {
        let state = self.state.must_lock();
        state.send_window.is_completed()
            && !(state.recv_window.is_completed() || self.stream_incoming_is_closed())
    }

    async fn recv_packet(
        &self,
        incoming_recv: &mut IncomingRecv,
        grace_period: Option<Instant>,
    ) -> Result<Option<(Packet, Timestamp)>, Error> {
        let mut recv_idle_interval = time::interval(*crate::recv_idle_timeout());
        tokio::pin! { let timeout = OptionFuture::from(grace_period.map(time::sleep_until)); }
        loop {
            tokio::select! {
                result = self.incoming_recv(incoming_recv) => {
                    return Some(result).transpose();
                }
                // TODO: `SendWindow` cannot notify us asynchronously of `is_completed` changes. To
                // work around this limitation, we continuously poll it when idle.
                _ = recv_idle_interval.tick() => {
                    if self.is_completed() {
                        return Ok(None);
                    }
                }
                Some(()) = &mut timeout => {
                    if self.is_only_recv_not_completed() {
                        return Err(Error::RecvGracePeriodExpired);
                    }
                    timeout.set(None.into());
                }
            }
        }
    }

    fn handle_packet(
        &self,
        recv_state: &mut RecvState,
        packet: Packet,
        recv_at: Timestamp,
    ) -> Result<(Vec<Packet>, Vec<Bytes>), Error> {
        let mut packets = Vec::new();
        let mut payloads = Vec::new();

        let packet_type = packet.header.packet_type();

        let mut state = self.state.must_lock();
        state
            .send_window
            .check_ack(packet.header.ack, &packet.selective_ack)?;

        state.update_send_delay(&packet.header, recv_at);

        match packet_type {
            PacketType::Data => {
                state.recv_window.recv(packet.header.seq, packet.payload)?;
                while let Some((_, payload)) = state.recv_window.next() {
                    payloads.push(payload);
                }
                packets.push(state.new_ack_packet());
            }
            PacketType::State => state
                .recv_window
                .check_state_packet_seq(packet.header.seq)?,
            PacketType::Finish => {
                tracing::debug!(seq = packet.header.seq, "receive eof");
                state.recv_window.close(packet.header.seq)?;
                if recv_state.grace_period.is_none() {
                    recv_state.grace_period = Some(Instant::now() + *crate::recv_grace_period());
                }
            }
            PacketType::Reset | PacketType::Synchronize => std::unreachable!(),
        }
        if !recv_state.fin_ack_sent {
            if let Some(packet) = state.new_fin_ack_packet() {
                packets.push(packet);
                recv_state.fin_ack_sent = true;
            }
        }

        if state
            .send_window
            .set_size(packet.header.seq, packet.header.window_size())
        {
            self.notifiers.send.notify_one();
        }

        // Only count ack in state packets.
        if packet_type == PacketType::State {
            state
                .send_window
                .recv_ack(packet.header.ack, &packet.selective_ack, recv_at);

            let rtt = &state.send_window.rtt;
            tracing::trace!(
                rtt = ?rtt.average,
                rtt_var = ?rtt.variance,
                rtt_timeout = ?rtt.timeout,
                "rtt update",
            );
            // TODO: Should we add a new notifier for RTT timeout changes?
            self.notifiers.rtt_timer.notify_one();
        }

        while state.send_window.remove() {
            self.notifiers.send.notify_one();
        }

        // BEP 29 does not seem to specify this, and libutp appears to apply congestion control
        // only when receiving an ack.
        if packet_type == PacketType::State {
            state.apply_control(packet.header.send_delay);
            self.notifiers.send.notify_one();
            tracing::trace!(
                window_size_limit = state.send_window.size_limit,
                "congestion control",
            );
        }

        let mut num_lost = 0;
        for seq in state.send_window.seqs().collect::<Vec<_>>() {
            if state.send_window.is_packet_lost(seq) {
                packets.push(state.make_resend_data_packet(seq)?.unwrap());
                num_lost += 1;
            }
        }
        if num_lost > 0 {
            // BEP 29 specifies that, to mimic TCP, the window size limit should be halved, when a
            // packet is lost.
            let new_size_limit = state.send_window.size_limit / 2;
            state.send_window.set_size_limit(new_size_limit);
            self.notifiers.send.notify_one();
            tracing::debug!(
                num_lost,
                window_size_limit = state.send_window.size_limit,
                "packet lost",
            );
        }

        Ok((packets, payloads))
    }
}

#[cfg(test)]
mod tests {
    use bytes::Bytes;
    use hex_literal::hex;
    use tokio::sync::mpsc;

    use super::{
        super::window::{RecvWindow, SendWindow},
        *,
    };

    fn new_state() -> Mutex<State> {
        Mutex::new(State::new(
            0x1000,
            0x1001,
            RecvWindow::new(10, 0x100),
            SendWindow::new(0, 0x200),
            150, // You cannot set the packet size smaller than the minimum packet size.
        ))
    }

    #[tokio::test]
    async fn recv() {
        let (actor, mut outgoing_recv, mut stream_incoming_recv) =
            Actor::new_mock(new_state(), "127.0.0.1:10000".parse().unwrap());
        actor.state.must_lock().send_window.close();
        let (incoming_send, incoming_recv) = mpsc::channel(8);
        incoming_send
            .send((
                Bytes::from_static(&hex!("11 00 1000 00000000 00000000 00000000 0102 0000")),
                Timestamp::ZERO,
            ))
            .await
            .unwrap();
        incoming_send
            .send((
                Bytes::from_static(&hex!(
                    "01 00 1000 00000000 00000000 00000000 0101 0000 1234"
                )),
                Timestamp::ZERO,
            ))
            .await
            .unwrap();
        assert_eq!(actor.is_completed(), false);

        assert_eq!(actor.recv(incoming_recv).await, Ok(()));
        assert_eq!(actor.is_completed(), true);
        drop(actor);

        let mut packets = Vec::new();
        while let Some(outgoing) = outgoing_recv.recv().await {
            packets.push(outgoing);
        }
        assert_eq!(packets.len(), 2);
        // ack
        let packet = &packets[0].1;
        assert_eq!(
            (packet.header.type_version & 0xf0) >> 4,
            PacketType::State as u8,
        );
        assert_eq!(packet.header.window_size, 10);
        assert_eq!(packet.header.seq, 0x200);
        assert_eq!(packet.header.ack, 0x101);
        // fin-ack
        let packet = &packets[1].1;
        assert_eq!(
            (packet.header.type_version & 0xf0) >> 4,
            PacketType::State as u8,
        );
        assert_eq!(packet.header.window_size, 10);
        assert_eq!(packet.header.seq, 0x200);
        assert_eq!(packet.header.ack, 0x102);

        let mut payloads = Vec::new();
        while let Some(payload) = stream_incoming_recv.recv().await {
            payloads.push(payload.unwrap());
        }
        assert_eq!(payloads, &[Bytes::from_static(&hex!("1234"))]);
    }

    #[tokio::test]
    async fn recv_unexpected_eof() {
        let (actor, _, _) = Actor::new_mock(new_state(), "127.0.0.1:10000".parse().unwrap());
        let (_, incoming_recv) = mpsc::channel(8);
        assert_eq!(actor.recv(incoming_recv).await, Err(Error::UnexpectedEof));
    }

    #[tokio::test]
    async fn recv_connection_reset() {
        let (actor, _, _) = Actor::new_mock(new_state(), "127.0.0.1:10000".parse().unwrap());
        let (incoming_send, incoming_recv) = mpsc::channel(8);
        incoming_send
            .send((
                Bytes::from_static(&hex!("31 00 1000 00000000 00000000 00000000 0000 0000")),
                Timestamp::ZERO,
            ))
            .await
            .unwrap();
        drop(incoming_send);
        assert_eq!(actor.recv(incoming_recv).await, Err(Error::ConnectionReset));
    }

    #[tokio::test]
    async fn recv_unexpected_resynchronize() {
        let (actor, _, _) = Actor::new_mock(new_state(), "127.0.0.1:10000".parse().unwrap());
        let (incoming_send, incoming_recv) = mpsc::channel(8);
        incoming_send
            .send((
                Bytes::from_static(&hex!("41 00 1000 00000000 00000000 00000000 0000 0000")),
                Timestamp::ZERO,
            ))
            .await
            .unwrap();
        drop(incoming_send);
        assert_eq!(
            actor.recv(incoming_recv).await,
            Err(Error::UnexpectedResynchronize),
        );
    }

    #[tokio::test]
    async fn recv_packet_timeout() {
        let (actor, _, _) = Actor::new_mock(new_state(), "127.0.0.1:10000".parse().unwrap());
        actor.state.must_lock().send_window.close();
        let (_incoming_send, mut incoming_recv) = mpsc::channel(8);
        assert_eq!(actor.is_completed(), true);
        assert_eq!(actor.is_only_recv_not_completed(), false);
        assert_eq!(
            actor
                .recv_packet(&mut incoming_recv, Some(Instant::now()))
                .await,
            Ok(None),
        );

        let (actor, _, _stream_incoming_recv) =
            Actor::new_mock(new_state(), "127.0.0.1:10000".parse().unwrap());
        actor.state.must_lock().send_window.close();
        let (_incoming_send, mut incoming_recv) = mpsc::channel(8);
        assert_eq!(actor.is_completed(), false);
        assert_eq!(actor.is_only_recv_not_completed(), true);
        assert_eq!(
            actor
                .recv_packet(&mut incoming_recv, Some(Instant::now()))
                .await,
            Err(Error::RecvGracePeriodExpired),
        );
    }
}
