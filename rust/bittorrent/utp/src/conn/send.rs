use std::sync::Mutex;

use bytes::BytesMut;
use tokio::time::{self, Instant};

use g1_base::sync::MutexExt;

use crate::bstream;

use super::{Error, actor::Actor, state::State};

impl Actor<Mutex<State>> {
    pub(super) async fn send(
        &self,
        mut stream_outgoing_recv: bstream::OutgoingRecv,
    ) -> Result<(), Error> {
        while let Some((mut payload, result_send)) = stream_outgoing_recv.recv().await {
            let result = self.send_payload(&mut payload).await;
            let _ = result_send.send((
                payload,
                result.as_ref().copied().map_err(Error::to_io_error),
            ));
            result?;
        }

        let finish_packet;
        {
            let mut state = self.state.must_lock();
            state.send_window.close();
            finish_packet = state.make_finish_packet();
        }

        self.outgoing_send(finish_packet).await?;

        tracing::debug!("utp connection actor send-half is completed");
        Ok(())
    }

    async fn send_payload(&self, payload: &mut BytesMut) -> Result<(), Error> {
        // We diverge from BEP 29 here: When the socket triggers a timeout (usually due to
        // `send_window` being full), we force the sending of a minimum-sized packet instead of
        // resetting `send_window.size_limit`.
        //
        // By the way, do not confuse socket timeout with packet timeout -- BEP 29 defines both.
        let mut now = Instant::now();
        let mut was_timeout = false;
        while !payload.is_empty() {
            let packet = self
                .state
                .must_lock()
                .make_data_packet(payload, was_timeout);
            match packet {
                Some(packet) => {
                    self.outgoing_send(packet).await?;
                    now = Instant::now();
                    was_timeout = false;
                }
                None => {
                    // This is roughly the time when `rtt_timer` returns `ResendLimitExceeded`.  It
                    // seems reasonable to use this value as the send timeout.
                    let send_timeout = self.state.must_lock().send_window.rtt.timeout
                        * (1 + *crate::resend_limit()).try_into().unwrap();
                    tokio::select! {
                        () = time::sleep_until(now + send_timeout) => {
                            tracing::debug!("send timeout");
                            was_timeout = true;
                        }
                        () = self.notifiers.send.notified() => {}
                    }
                }
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::net::SocketAddr;
    use std::time::Duration;

    use tokio::sync::{mpsc, oneshot};

    use crate::packet::{Packet, PacketType};

    use super::{
        super::window::{RecvWindow, SendWindow},
        *,
    };

    const SEND_WINDOW_SIZE: usize = 200;

    fn new_state() -> Mutex<State> {
        let state = Mutex::new(State::new(
            100,
            101,
            RecvWindow::new(0, 1000),
            SendWindow::new(SEND_WINDOW_SIZE, 2000),
            150, // You cannot set the packet size smaller than the minimum packet size.
        ));
        state.must_lock().send_window.set_size(0, SEND_WINDOW_SIZE);
        state
    }

    fn assert_state(state: &Mutex<State>, seq: u16, inflights: &[(u16, &[u8])]) {
        let state = state.must_lock();
        assert_eq!(state.send_window.seq, seq);
        assert_eq!(
            state
                .send_window
                .inflights()
                .iter()
                .map(|inflight| (inflight.seq, inflight.payload.as_ref()))
                .collect::<Vec<_>>(),
            inflights,
        );
    }

    fn assert_data_packets(packets: &[(SocketAddr, Packet)], expect: &[(u16, &[u8])]) {
        assert_eq!(packets.len(), expect.len());
        for ((_, packet), (seq, payload)) in packets.iter().zip(expect.iter()) {
            assert_eq!(
                (packet.header.type_version & 0xf0) >> 4,
                PacketType::Data as u8
            );
            assert_eq!(packet.header.seq, *seq);
            assert_eq!(packet.payload, payload);
        }
    }

    #[tokio::test]
    async fn send() {
        let (actor, mut outgoing_recv, _) =
            Actor::new_mock(new_state(), "127.0.0.1:10000".parse().unwrap());
        assert_state(&actor.state, 2000, &[]);

        let (stream_outgoing_send, stream_outgoing_recv) = mpsc::channel(8);
        let (result_send, result_recv) = oneshot::channel();
        stream_outgoing_send
            .send((BytesMut::from(&b"Hello, world!"[..]), result_send))
            .await
            .unwrap();
        drop(stream_outgoing_send);

        assert_eq!(actor.send(stream_outgoing_recv).await, Ok(()));
        let (buffer, result) = result_recv.await.unwrap();
        assert_eq!(buffer.is_empty(), true);
        assert_matches!(result, Ok(()));
        assert_state(&actor.state, 2002, &[(2000, b"Hello, world!")]);

        drop(actor);
        let mut packets = Vec::new();
        while let Some(outgoing) = outgoing_recv.recv().await {
            packets.push(outgoing);
        }
        assert_eq!(packets.len(), 2);
        assert_data_packets(&packets[0..1], &[(2000, b"Hello, world!")]);
        assert_eq!(
            (packets[1].1.header.type_version & 0xf0) >> 4,
            PacketType::Finish as u8,
        );
        assert_eq!(packets[1].1.header.seq, 2001);
    }

    #[tokio::test]
    async fn send_payload() {
        let (actor, mut outgoing_recv, _) =
            Actor::new_mock(new_state(), "127.0.0.1:10000".parse().unwrap());
        actor.state.must_lock().send_window.rtt.timeout = Duration::ZERO;
        assert_state(&actor.state, 2000, &[]);

        let mut data = [0u8; SEND_WINDOW_SIZE];
        for i in 0..data.len() {
            data[i] = (i % 256).try_into().unwrap();
        }

        let mut payload = BytesMut::from(&data[..]);
        assert_eq!(actor.send_payload(&mut payload).await, Ok(()));
        assert_eq!(payload.is_empty(), true);
        assert_state(
            &actor.state,
            2002,
            // 130 == packet size - header size
            &[(2000, &data[..130]), (2001, &data[130..])],
        );

        drop(actor);
        let mut packets = Vec::new();
        while let Some(outgoing) = outgoing_recv.recv().await {
            packets.push(outgoing);
        }
        assert_data_packets(&packets, &[(2000, &data[..130]), (2001, &data[130..])]);
    }

    #[tokio::test]
    async fn send_payload_timeout() {
        let (actor, mut outgoing_recv, _) =
            Actor::new_mock(new_state(), "127.0.0.1:10000".parse().unwrap());
        actor.state.must_lock().send_window.rtt.timeout = Duration::ZERO;
        assert_state(&actor.state, 2000, &[]);

        let mut data = [0u8; SEND_WINDOW_SIZE + 130 + 1];
        for i in 0..data.len() {
            data[i] = (i % 256).try_into().unwrap();
        }

        let mut payload = BytesMut::from(&data[..]);
        assert_eq!(actor.send_payload(&mut payload).await, Ok(()));
        assert_eq!(payload.is_empty(), true);
        assert_state(
            &actor.state,
            2004,
            // 130 == packet size - header size
            &[
                (2000, &data[..130]),
                (2001, &data[130..SEND_WINDOW_SIZE]),
                (2002, &data[SEND_WINDOW_SIZE..SEND_WINDOW_SIZE + 130]),
                (2003, &data[SEND_WINDOW_SIZE + 130..]),
            ],
        );

        drop(actor);
        let mut packets = Vec::new();
        while let Some(outgoing) = outgoing_recv.recv().await {
            packets.push(outgoing);
        }
        assert_data_packets(
            &packets,
            &[
                (2000, &data[..130]),
                (2001, &data[130..SEND_WINDOW_SIZE]),
                (2002, &data[SEND_WINDOW_SIZE..SEND_WINDOW_SIZE + 130]),
                (2003, &data[SEND_WINDOW_SIZE + 130..]),
            ],
        );
    }
}
