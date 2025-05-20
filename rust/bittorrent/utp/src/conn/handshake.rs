use bytes::Bytes;
use snafu::prelude::*;
use tokio::time;

use crate::packet::{Packet, PacketType};
use crate::timestamp::{self, Timestamp};

use super::{
    Error, ExpectPacketTypeSnafu, IncomingRecv, InvalidPacketSnafu,
    actor::Actor,
    state::State,
    window::{RecvWindow, SendWindow},
};

#[derive(Debug)]
pub(crate) struct Handshake {
    recv_id: u16,
    send_id: u16,
    seq: u16,
    ack: u16,
    recv_window_size: usize,
    send_window_size_limit: usize,
    packet_size: usize,
}

impl Handshake {
    pub(crate) fn new_connect() -> Self {
        let recv_id = rand::random();
        Self::new(
            recv_id,
            recv_id.wrapping_add(1),
            // BEP 29 specifies that seq should be initialized to 1, but libutp initializes it with
            // a random value.
            rand::random(),
        )
    }

    pub(crate) fn new_accept() -> Self {
        Self::new(0, 0, rand::random())
    }

    fn new(recv_id: u16, send_id: u16, seq: u16) -> Self {
        Self {
            recv_id,
            send_id,
            seq,
            ack: 0,
            recv_window_size: *crate::recv_window_size(),
            send_window_size_limit: *crate::send_window_size_limit(),
            packet_size: *crate::packet_size(),
        }
    }

    fn next_seq(&mut self) -> u16 {
        let seq = self.seq;
        self.seq = self.seq.wrapping_add(1);
        seq
    }

    fn make_synchronize_packet(&mut self) -> Packet {
        Packet::new(
            PacketType::Synchronize,
            self.recv_id,
            timestamp::now(),
            0,
            self.recv_window_size,
            self.next_seq(),
            self.ack,
            None,
            Bytes::new(),
        )
    }

    fn new_syn_ack_packet(&self) -> Packet {
        Packet::new(
            PacketType::State,
            self.send_id,
            timestamp::now(),
            0,
            self.recv_window_size,
            // The handshake flowchart in BEP 29 specifies that seq is post-incremented, but it
            // appears that libutp does not implement the post-increment.
            self.seq,
            self.ack,
            None,
            Bytes::new(),
        )
    }

    fn new_state(&self) -> State {
        State::new(
            self.recv_id,
            self.send_id,
            RecvWindow::new(self.recv_window_size, self.ack),
            SendWindow::new(self.send_window_size_limit, self.seq),
            self.packet_size,
        )
    }
}

impl Actor<Handshake> {
    pub(super) async fn handshake(
        &mut self,
        incoming_recv: &mut IncomingRecv,
    ) -> Result<State, Error> {
        if self.state.recv_id != self.state.send_id {
            self.connect(incoming_recv).await
        } else {
            self.accept(incoming_recv).await
        }
    }

    // TODO: Should we send a reset to the peer on error?
    async fn connect(&mut self, incoming_recv: &mut IncomingRecv) -> Result<State, Error> {
        let outgoing_packet = self.state.make_synchronize_packet();
        self.outgoing_send(outgoing_packet).await?;

        let (packet, recv_at) = time::timeout(
            *crate::connect_timeout(),
            self.incoming_recv(incoming_recv, Some(self.state.recv_id)),
        )
        .await
        .map_err(|_| Error::ConnectTimeout)??;
        let packet_type = packet.header.packet_type();
        ensure!(
            packet_type == PacketType::State,
            ExpectPacketTypeSnafu {
                packet_type,
                expect: PacketType::State,
            },
        );
        // NOTE: BPE 29 specifies that ack should be set to seq, but for unknown reasons, libutp
        // sets ack to seq - 1.  If I have to guess, it is probably because the accept side of the
        // code in libutp does not post-increment seq when sending the syn-ack packet.
        self.state.ack = packet.header.seq.wrapping_sub(1);

        let mut state = self.state.new_state();
        state.update_send_delay(&packet.header, recv_at);
        state
            .send_window
            .set_size(packet.header.seq, packet.header.window_size());

        tracing::debug!(
            seq = state.send_window.seq,
            ack = state.recv_window.ack(),
            "connect",
        );
        Ok(state)
    }

    async fn accept(&mut self, incoming_recv: &mut IncomingRecv) -> Result<State, Error> {
        let (packet, recv_at) = time::timeout(
            *crate::accept_timeout(),
            self.incoming_recv(incoming_recv, None),
        )
        .await
        .map_err(|_| Error::AcceptTimeout)??;
        let packet_type = packet.header.packet_type();
        ensure!(
            packet_type == PacketType::Synchronize,
            ExpectPacketTypeSnafu {
                packet_type,
                expect: PacketType::Synchronize,
            },
        );
        self.state.recv_id = packet.header.conn_id.wrapping_add(1);
        self.state.send_id = packet.header.conn_id;
        self.state.ack = packet.header.seq;

        let outgoing_packet = self.state.new_syn_ack_packet();
        self.outgoing_send(outgoing_packet).await?;

        let mut state = self.state.new_state();
        state.update_send_delay(&packet.header, recv_at);
        state
            .send_window
            .set_size(packet.header.seq, packet.header.window_size());

        tracing::debug!(
            seq = state.send_window.seq,
            ack = state.recv_window.ack(),
            "accept",
        );
        Ok(state)
    }

    async fn incoming_recv(
        &self,
        incoming_recv: &mut IncomingRecv,
        conn_id: Option<u16>,
    ) -> Result<(Packet, Timestamp), Error> {
        loop {
            let (packet, recv_at) = incoming_recv.recv().await.ok_or(Error::UnexpectedEof)?;
            let packet = Packet::try_from(packet).context(InvalidPacketSnafu)?;
            let expect = conn_id.unwrap_or(packet.header.conn_id);
            if packet.header.conn_id == expect {
                tracing::trace!(
                    ?packet.header,
                    ?packet.selective_ack,
                    payload_size = packet.payload.len(),
                    "recv",
                );
                return Ok((packet, recv_at));
            }
            tracing::warn!(
                conn_id = packet.header.conn_id,
                expect,
                "receive unexpected conn id",
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use bytes::BytesMut;
    use tokio::sync::mpsc;

    use super::{
        super::{IncomingSend, OutgoingRecv},
        *,
    };

    #[tokio::test]
    async fn handshake() {
        async fn forward(mut outgoing_recv: OutgoingRecv, incoming_send: IncomingSend) {
            while let Some((_, packet)) = outgoing_recv.recv().await {
                let mut buffer = BytesMut::with_capacity(packet.size());
                packet.encode(&mut buffer);
                if incoming_send
                    .send((buffer.freeze(), Timestamp::ZERO))
                    .await
                    .is_err()
                {
                    break;
                }
            }
        }

        let (mut connector, connector_outgoing_recv, _) =
            Actor::new_mock(Handshake::new_connect(), "127.0.0.1:10000".parse().unwrap());
        let (mut acceptor, acceptor_outgoing_recv, _) =
            Actor::new_mock(Handshake::new_accept(), "127.0.0.1:20000".parse().unwrap());

        let (connector_incoming_send, mut connector_incoming_recv) = mpsc::channel(32);
        let (acceptor_incoming_send, mut acceptor_incoming_recv) = mpsc::channel(32);

        let connector_forward_task =
            tokio::spawn(forward(connector_outgoing_recv, acceptor_incoming_send));
        let acceptor_forward_task =
            tokio::spawn(forward(acceptor_outgoing_recv, connector_incoming_send));

        let connector_task = tokio::spawn(async move {
            let state = connector.handshake(&mut connector_incoming_recv).await?;
            Ok::<_, Error>((connector, connector_incoming_recv, state))
        });
        let acceptor_task = tokio::spawn(async move {
            let state = acceptor.handshake(&mut acceptor_incoming_recv).await?;
            Ok::<_, Error>((acceptor, acceptor_incoming_recv, state))
        });

        let (connector, connector_incoming_recv, connector_state) =
            connector_task.await.unwrap().unwrap();
        let (acceptor, acceptor_incoming_recv, acceptor_state) =
            acceptor_task.await.unwrap().unwrap();

        assert_eq!(connector_state.recv_id, acceptor_state.send_id);
        assert_eq!(connector_state.send_id, acceptor_state.recv_id);

        assert_eq!(
            connector_state.recv_window.in_order_seq(),
            acceptor_state.send_window.seq.wrapping_sub(1),
        );
        assert_eq!(
            connector_state.recv_window.ack(),
            acceptor_state.send_window.seq.wrapping_sub(1),
        );
        assert_eq!(
            acceptor_state.recv_window.in_order_seq(),
            connector_state.send_window.seq.wrapping_sub(1),
        );
        assert_eq!(
            acceptor_state.recv_window.ack(),
            connector_state.send_window.seq.wrapping_sub(1),
        );

        assert_eq!(
            connector_state.send_window.size(),
            acceptor.state.recv_window_size
        );
        assert_eq!(
            acceptor_state.send_window.size(),
            connector.state.recv_window_size
        );

        drop(connector);
        drop(acceptor);
        drop(connector_incoming_recv);
        drop(acceptor_incoming_recv);
        connector_forward_task.await.unwrap();
        acceptor_forward_task.await.unwrap();
    }
}
