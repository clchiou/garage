use std::cmp;
use std::time::Duration;

use bytes::{Bytes, BytesMut};
use snafu::prelude::*;

use crate::packet::{Packet, PacketHeader, PacketType, SelectiveAck};
use crate::timestamp::{self, Timestamp};

use super::{
    control::DelayWindow,
    window::{RecvWindow, SendWindow},
    Error, ResendLimitExceededSnafu, MIN_PACKET_SIZE,
};

#[derive(Debug)]
pub(super) struct State {
    pub(super) recv_id: u16,
    pub(super) send_id: u16,
    pub(super) recv_window: RecvWindow,
    pub(super) send_window: SendWindow,
    pub(super) send_delay: u32,
    pub(super) delay_window: DelayWindow,
    pub(super) packet_size: usize,
}

impl State {
    pub(super) fn new(
        recv_id: u16,
        send_id: u16,
        recv_window: RecvWindow,
        send_window: SendWindow,
        packet_size: usize,
    ) -> Self {
        Self {
            recv_id,
            send_id,
            recv_window,
            send_window,
            send_delay: 0,
            delay_window: DelayWindow::new(
                Duration::from_secs(120), // Window size specified by BEP 29.
            ),
            packet_size: cmp::max(packet_size, MIN_PACKET_SIZE),
        }
    }

    // NOTE: You must call this method whenever you receive a packet.
    pub(super) fn update_send_delay(&mut self, header: &PacketHeader, recv_at: Timestamp) {
        self.send_delay = timestamp::as_micros_u32(recv_at).wrapping_sub(header.send_at);
        // BEP 29 specifies that we should ignore `header.send_delay` when it is 0, indicating that
        // the socket is newly opened.
        if header.send_delay != 0 {
            self.delay_window.push(recv_at, header.send_delay);
        }
    }

    /// Updates `send_window.size_limit` in accordance with the congestion control algorithm
    /// specified by BEP 29.
    pub(super) fn apply_control(&mut self, send_delay: u32) {
        // BEP 29 does not specify `window_factor` value when `used` or `size_limit` is 0.  This is
        // what libutp appears to do.
        if self.send_window.used == 0 {
            return;
        }
        let window_factor = to_f64(cmp::min(self.send_window.used, self.send_window.size_limit))
            / to_f64(cmp::max(self.send_window.used, self.send_window.size_limit));

        let target = f64::from(
            u32::try_from(crate::congestion_control_target().as_micros() % (1 << u32::BITS))
                .unwrap(),
        );
        let off_target = target - f64::from(self.delay_window.subtract_min_delay(send_delay));
        let delay_factor = off_target / target;

        // Again, BEP 29 does not explicitly specify this, but it appears that libutp restricts the
        // range of `scale_gain`.
        let scale_gain_limit = to_f64(*crate::max_congestion_window_increase_per_rtt());
        let scale_gain = (scale_gain_limit * delay_factor * window_factor)
            .clamp(-scale_gain_limit, scale_gain_limit);
        let scale_gain = unsafe { scale_gain.to_int_unchecked::<isize>() };

        self.send_window.set_size_limit(
            self.send_window
                .size_limit
                .saturating_add_signed(scale_gain),
        );
    }

    pub(super) fn set_packet_size(&mut self, packet_size: usize) {
        self.packet_size = cmp::max(packet_size, MIN_PACKET_SIZE);
    }

    pub(super) fn make_data_packet(&mut self, data: &mut BytesMut, force: bool) -> Option<Packet> {
        let reserved = self.send_window.reserve(cmp::min(
            // For now, data packets do not have extensions.
            self.packet_size - PacketHeader::SIZE,
            data.len(),
        ));
        let payload_size = if reserved != 0 {
            reserved
        } else if force {
            // For now, data packets do not have extensions.
            cmp::min(MIN_PACKET_SIZE - PacketHeader::SIZE, data.len())
        } else {
            return None;
        };
        let payload = data.split_to(payload_size).freeze();
        // It is okay to call `Bytes::clone` because it shares the underlying buffer and,
        // therefore, is very cheap.
        let seq = self.send_window.push(payload.clone());
        Some(self.new_data_packet(seq, payload))
    }

    pub(super) fn make_resend_data_packet(&mut self, seq: u16) -> Result<Option<Packet>, Error> {
        let inflight = match self.send_window.get_mut(seq) {
            Some(inflight) => inflight,
            None => return Ok(None),
        };
        ensure!(
            inflight.num_resends < *crate::resend_limit(),
            ResendLimitExceededSnafu { seq },
        );
        // It is okay to call `Bytes::clone` because it shares the underlying buffer and,
        // therefore, is very cheap.
        let payload = inflight.payload.clone();
        // TODO: This is not the exact time when the packet is sent, but it should be close enough
        // for now.
        inflight.set_send_at(timestamp::now());
        inflight.increment_resend();
        Ok(Some(self.new_data_packet(seq, payload)))
    }

    fn new_data_packet(&self, seq: u16, payload: Bytes) -> Packet {
        self.new_packet(
            PacketType::Data,
            seq,
            self.recv_window.last_ack,
            None, // For now, data packets do not have extensions.
            payload,
        )
    }

    pub(super) fn make_ack_packet(&mut self) -> Option<Packet> {
        let (ack, selective_ack) = self.recv_window.next_ack()?;
        Some(self.new_packet(
            PacketType::State,
            self.send_window.seq,
            ack,
            selective_ack,
            Bytes::new(),
        ))
    }

    pub(super) fn new_fin_ack_packet(&self) -> Option<Packet> {
        if self.recv_window.is_completed() {
            Some(self.new_packet(
                PacketType::State,
                self.send_window.seq,
                self.recv_window.eof.unwrap(),
                None,
                Bytes::new(),
            ))
        } else {
            None
        }
    }

    pub(super) fn make_finish_packet(&mut self) -> Packet {
        // BEP 29 seems to suggest that seq is not post-incremented when making a finish packet,
        // but libutp post-increments it.  Here, we mimic libutp.
        //
        // TODO: What is the seq if we send another finish packet?
        let seq = self.send_window.next_seq();
        self.new_packet(
            PacketType::Finish,
            seq,
            self.recv_window.last_ack,
            None,
            Bytes::new(),
        )
    }

    pub(super) fn new_reset_packet(&self) -> Packet {
        self.new_packet(
            PacketType::Reset,
            self.send_window.seq,
            self.recv_window.last_ack,
            None,
            Bytes::new(),
        )
    }

    fn new_packet(
        &self,
        packet_type: PacketType,
        seq: u16,
        ack: u16,
        selective_ack: Option<SelectiveAck>,
        payload: Bytes,
    ) -> Packet {
        Packet::new(
            packet_type,
            self.send_id,
            timestamp::now(),
            self.send_delay,
            self.recv_window.size(),
            seq,
            ack,
            selective_ack,
            payload,
        )
    }
}

fn to_f64(x: usize) -> f64 {
    u32::try_from(x).unwrap().into()
}
