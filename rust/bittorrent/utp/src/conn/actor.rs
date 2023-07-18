use std::net::SocketAddr;
use std::sync::{Arc, Mutex};

use bytes::Bytes;
use snafu::prelude::*;
use tokio::{
    net::UdpSocket,
    sync::{mpsc, Notify},
    time,
};

use g1_base::sync::MutexExt;

use crate::bstream::{self, UtpRecvStream, UtpSendStream, UtpStream};
use crate::packet::{Packet, PacketType};
use crate::timestamp::Timestamp;

use super::{
    handshake::Handshake, state::State, ConnectedSend, Error, IncomingRecv, IncomingSend,
    InvalidPacketSnafu, OutgoingSend,
};

#[derive(Debug)]
pub(crate) struct Actor<S = InitState> {
    pub(super) state: S,
    peer_endpoint: SocketAddr,
    outgoing_send: OutgoingSend,
    stream_incoming_send: bstream::IncomingSend,
    pub(super) notifiers: Notifiers,
}

#[derive(Debug)]
pub(crate) struct InitState {
    handshake: Handshake,
    connected_send: ConnectedSend,
    incoming_recv: IncomingRecv,
    stream_outgoing_recv: bstream::OutgoingRecv,
}

#[derive(Debug)]
pub(super) struct Notifiers {
    /// When notified, `send` should be awakened, which may then try to send packets.
    pub(super) send: Notify,
    /// When notified, the RTT timer should be reset.
    pub(super) rtt_timer: Notify,
}

impl Actor<InitState> {
    pub(crate) fn new(
        handshake: Handshake,
        peer_endpoint: SocketAddr,
        connected_send: ConnectedSend,
        outgoing_send: OutgoingSend,
        stream_incoming_send: bstream::IncomingSend,
        stream_outgoing_recv: bstream::OutgoingRecv,
    ) -> (Self, IncomingSend) {
        let (incoming_send, incoming_recv) = mpsc::channel(*super::incoming_queue_size());
        (
            Self {
                state: InitState {
                    handshake,
                    connected_send,
                    incoming_recv,
                    stream_outgoing_recv,
                },
                peer_endpoint,
                outgoing_send,
                stream_incoming_send,
                notifiers: Notifiers::new(),
            },
            incoming_send,
        )
    }

    pub(crate) fn with_socket(
        handshake: Handshake,
        socket: Arc<UdpSocket>,
        peer_endpoint: SocketAddr,
        connected_send: ConnectedSend,
        outgoing_send: OutgoingSend,
    ) -> ((Self, IncomingSend), UtpStream) {
        let (recv, stream_incoming_send) = UtpRecvStream::new(socket.clone(), peer_endpoint);
        let (send, stream_outgoing_recv) = UtpSendStream::new(socket, peer_endpoint);
        (
            Self::new(
                handshake,
                peer_endpoint,
                connected_send,
                outgoing_send,
                stream_incoming_send,
                stream_outgoing_recv,
            ),
            UtpStream::new(recv, send),
        )
    }

    pub(crate) async fn run(self) -> Result<(), Error> {
        let (this, init) = self.into_state(());
        let InitState {
            handshake,
            connected_send,
            mut incoming_recv,
            stream_outgoing_recv,
        } = init;
        let (mut this, _) = this.into_state(handshake);

        let state = match this.handshake(&mut incoming_recv).await {
            Ok(state) => state,
            Err(Error::ExpectPacketType {
                packet_type: PacketType::Reset,
                expect: PacketType::Synchronize,
            }) => {
                // This is probably the result of an earlier connection reset.  We may ignore it
                // and close the connection.
                tracing::debug!("expect synchronize but receive reset");
                return Ok(());
            }
            Err(error) => {
                let _ = connected_send.send(Err(error.to_io_error()));
                return Err(error);
            }
        };
        let _ = connected_send.send(Ok(()));
        // Wrap the state in a `Mutex` in order to work around the "single mutable borrow" rule in
        // the `tokio::try_join!` block.
        let (this, _) = this.into_state(Mutex::new(state));

        // Unlike TCP, BEP 29 does not specify the protocol for closing a connection.  Therefore,
        // we simply send a reset and do not wait for any response from the peer.
        let packet = this.state.must_lock().new_reset_packet();
        this.outgoing_send(packet).await?;

        Ok(())
    }
}

impl<S> Actor<S> {
    pub(super) fn into_state<T>(self, next_state: T) -> (Actor<T>, S) {
        (
            Actor {
                state: next_state,
                peer_endpoint: self.peer_endpoint,
                outgoing_send: self.outgoing_send,
                stream_incoming_send: self.stream_incoming_send,
                notifiers: self.notifiers,
            },
            self.state,
        )
    }

    pub(super) async fn outgoing_send(&self, packet: Packet) -> Result<(), Error> {
        self.outgoing_send_dont_reset_rtt_timer(packet).await?;
        self.notifiers.rtt_timer.notify_one();
        Ok(())
    }

    pub(super) async fn outgoing_send_dont_reset_rtt_timer(
        &self,
        packet: Packet,
    ) -> Result<(), Error> {
        tracing::trace!(
            ?packet.header,
            ?packet.selective_ack,
            payload_size = packet.payload.len(),
            "send",
        );
        self.outgoing_send
            .send((self.peer_endpoint, packet))
            .await
            .map_err(|_| Error::BrokenPipe)
    }

    pub(super) fn stream_incoming_is_closed(&self) -> bool {
        self.stream_incoming_send.is_closed()
    }

    pub(super) async fn stream_incoming_send(&self, payload: Bytes) -> Result<bool, Error> {
        // If it returns a `SendError`, it means that the `UtpRecvStream` was dropped, and in this
        // case, the actor should simply drop the payload.
        Ok(time::timeout(
            *crate::recv_buffer_timeout(),
            self.stream_incoming_send.send(Ok(payload)),
        )
        .await
        .map_err(|_| Error::RecvBufferTimeout)?
        .is_ok())
    }

    pub(super) fn abort_stream(&self, error: &Error) {
        let _ = self.stream_incoming_send.try_send(Err(error.to_io_error()));
    }
}

impl Actor<Mutex<State>> {
    pub(super) async fn incoming_recv(
        &self,
        incoming_recv: &mut IncomingRecv,
    ) -> Result<(Packet, Timestamp), Error> {
        loop {
            let (packet, recv_at) = incoming_recv.recv().await.ok_or(Error::UnexpectedEof)?;
            let packet = Packet::try_from(packet).context(InvalidPacketSnafu)?;
            let recv_id = self.state.must_lock().recv_id;
            if packet.header.conn_id == recv_id {
                tracing::trace!(
                    ?packet.header,
                    ?packet.selective_ack,
                    payload_size = packet.payload.len(),
                    "recv",
                );
                self.notifiers.rtt_timer.notify_one();
                return Ok((packet, recv_at));
            }
            tracing::warn!(
                conn_id = packet.header.conn_id,
                expect = recv_id,
                "receive unexpected conn id",
            );
        }
    }

    pub(super) fn abort_peer(&self) {
        let packet = self.state.must_lock().new_reset_packet();
        tracing::trace!(
            ?packet.header,
            ?packet.selective_ack,
            payload_size = packet.payload.len(),
            "send",
        );
        let _ = self.outgoing_send.try_send((self.peer_endpoint, packet));
    }
}

impl Notifiers {
    fn new() -> Self {
        Self {
            send: Notify::new(),
            rtt_timer: Notify::new(),
        }
    }
}

#[cfg(test)]
mod test_harness {
    use super::{super::OutgoingRecv, *};

    impl<S> Actor<S> {
        pub(crate) fn new_mock(
            state: S,
            peer_endpoint: SocketAddr,
        ) -> (Self, OutgoingRecv, bstream::IncomingRecv) {
            let (outgoing_send, outgoing_recv) = mpsc::channel(32);
            let (stream_incoming_send, stream_incoming_recv) = mpsc::channel(32);
            (
                Self {
                    state,
                    peer_endpoint,
                    outgoing_send,
                    stream_incoming_send,
                    notifiers: Notifiers::new(),
                },
                outgoing_recv,
                stream_incoming_recv,
            )
        }
    }
}
