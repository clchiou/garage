use std::cmp;
use std::collections::{HashSet, VecDeque};
use std::mem;
use std::ops::RangeInclusive;

use bitvec::prelude::*;
use bytes::Bytes;
use snafu::prelude::*;

use crate::packet::SelectiveAck;
use crate::timestamp::{self, Timestamp};

use super::{
    rtt::Rtt, AckExceedSeqSnafu, DifferentEofSnafu, DistantSeqSnafu, Error, SeqExceedEofSnafu,
};

#[derive(Debug)]
pub(super) struct RecvWindow {
    size: isize,

    // These fields are used to track the out-of-order arrival of packets.  The next seq is
    // `in_order_seq` plus one.
    in_order_seq: u16,
    packets: VecDeque<Option<(u16, Bytes)>>,

    pub(super) last_ack: u16,
    recv_seqs: HashSet<u16>,

    pub(super) eof: Option<u16>,
}

#[derive(Debug)]
pub(super) struct SendWindow {
    pub(super) used: usize,
    size_seq: Option<u16>,
    size: usize,
    // This is tuned by the congestion control algorithm.
    pub(super) size_limit: usize,

    pub(super) seq: u16,
    inflights: VecDeque<Inflight>,
    /// `Inflight::num_acks` of the last removed `inflights` entry, which is referred to by
    /// `is_packet_lost`.
    last_num_acks: Option<(u16, usize)>,

    pub(super) rtt: Rtt,

    eof: bool,
}

#[derive(Debug)]
pub(super) struct Inflight {
    pub(super) seq: u16,
    pub(super) payload: Bytes,

    send_at: Timestamp,
    pub(super) num_resends: usize,

    pub(super) num_acks: usize,
}

/// Measures the distance between two seqs.
fn measure(origin_seq: u16, target_seq: u16) -> i32 {
    const N: i32 = 1 << u16::BITS;
    let distance = i32::from(target_seq) - i32::from(origin_seq);
    let wraparound = -distance.signum() * (N - distance.abs());
    if distance.abs() <= wraparound.abs() {
        distance
    } else {
        wraparound
    }
}

/// Computes an ordinary ack and selective acks based on the last ack and the received seqs.
fn compute_ack(last_ack: u16, recv_seqs: HashSet<u16>) -> (u16, Option<SelectiveAck>) {
    fn compute_selective_ack(base: usize, ds: &[i32]) -> Option<SelectiveAck> {
        fn bitmask_index(base: usize, d: i32) -> usize {
            usize::try_from(d).unwrap() - base
        }

        if ds.is_empty() {
            return None;
        }
        let num_bits = bitmask_index(base, ds[ds.len() - 1]) + 1;
        let size = num_bits / 8 + if num_bits % 8 != 0 { 1 } else { 0 };
        let size = size - size % 4 + if size % 4 != 0 { 4 } else { 0 };
        let mut bitmask = vec![0u8; size];
        let bits = bitmask.view_bits_mut::<Lsb0>();
        for d in ds {
            bits.set(bitmask_index(base, *d), true);
        }
        Some(SelectiveAck(bitmask.into()))
    }

    let mut ds: Vec<_> = recv_seqs
        .iter()
        .copied()
        .map(|seq| measure(last_ack, seq))
        .collect();
    ds.sort();
    match ds.binary_search(&1) {
        Ok(i) => {
            // Find the position of the first non-consecutive value in `ds[i..]`.
            let mut n = 1;
            while i + n < ds.len() {
                if ds[i + n - 1] + 1 != ds[i + n] {
                    break;
                }
                n += 1;
            }
            (
                last_ack.wrapping_add(u16::try_from(n).unwrap()),
                compute_selective_ack(2 + n, &ds[i + n..]),
            )
        }
        Err(i) => (last_ack, compute_selective_ack(2, &ds[i..])),
    }
}

fn iter_bitmask(bitmask: &Bytes, ack: u16) -> impl Iterator<Item = u16> + '_ {
    bitmask
        .view_bits::<Lsb0>()
        .iter_ones()
        .map(move |i| ack.wrapping_add(u16::try_from(2 + i).unwrap()))
}

impl RecvWindow {
    pub(super) fn new(size: usize, ack: u16) -> Self {
        Self {
            size: size.try_into().unwrap(),
            in_order_seq: ack,
            packets: VecDeque::new(),
            last_ack: ack,
            recv_seqs: HashSet::new(),
            eof: None,
        }
    }

    pub(super) fn size(&self) -> usize {
        if self.size >= 0 {
            usize::try_from(self.size).unwrap()
        } else {
            0
        }
    }

    pub(super) fn is_completed(&self) -> bool {
        match self.eof {
            Some(eof) => measure(self.in_order_seq, eof) == 1,
            None => false,
        }
    }

    pub(super) fn close(&mut self, eof: u16) -> Result<(), Error> {
        if let Some(old) = self.eof {
            ensure!(eof == old, DifferentEofSnafu { old, new: eof });
        }
        self.eof = Some(eof);
        Ok(())
    }

    pub(super) fn check_state_packet_seq(&self, seq: u16) -> Result<(), Error> {
        if let Some(eof) = self.eof {
            // libutp post-increments seq when making the finish packet.  Thus, the seq of state
            // packets that are received after the finish packet is eof + 1.
            ensure!(measure(seq, eof) >= -1, SeqExceedEofSnafu { seq, eof });
        }
        Ok(())
    }

    // TODO: Should we include the size of the packet header and the extension when updating
    // `self.size`?
    pub(super) fn recv(&mut self, seq: u16, payload: Bytes) -> Result<bool, Error> {
        /// We reject seq that is too far away from `in_order_seq`.
        const RECV_ACCEPT_SEQ_RANGE: RangeInclusive<i32> = -16..=64;

        if let Some(eof) = self.eof {
            ensure!(measure(seq, eof) > 0, SeqExceedEofSnafu { seq, eof });
        }

        let d = measure(self.in_order_seq, seq);
        ensure!(
            RECV_ACCEPT_SEQ_RANGE.contains(&d),
            DistantSeqSnafu {
                seq,
                in_order_seq: self.in_order_seq,
            },
        );

        self.recv_seqs.insert(seq);

        if d < 1 {
            tracing::debug!(
                in_order_seq = self.in_order_seq,
                seq,
                "receive duplicated packet seq",
            );
            return Ok(false);
        }
        let i = usize::try_from(d - 1).unwrap();

        if i >= self.packets.len() {
            self.packets.reserve(i - self.packets.len() + 1);
            for _ in self.packets.len()..=i {
                self.packets.push_back(None);
            }
        }

        let packet = self.packets.get_mut(i).unwrap();
        if packet.is_some() {
            tracing::debug!(
                in_order_seq = self.in_order_seq,
                seq,
                "receive duplicated packet seq",
            );
            return Ok(false);
        }

        self.size -= isize::try_from(payload.len()).unwrap();
        *packet = Some((seq, payload));
        Ok(true)
    }

    pub(super) fn next(&mut self) -> Option<(u16, Bytes)> {
        if measure(self.in_order_seq, self.packets.front()?.as_ref()?.0) != 1 {
            return None;
        }
        let packet = self.packets.pop_front().unwrap();
        let (seq, payload) = packet.as_ref().unwrap();
        self.in_order_seq = *seq;
        self.size += isize::try_from(payload.len()).unwrap();
        packet
    }

    pub(super) fn next_ack(&mut self) -> Option<(u16, Option<SelectiveAck>)> {
        let recv_seqs = mem::take(&mut self.recv_seqs);
        if recv_seqs.is_empty() {
            None
        } else {
            let (ack, selective_ack) = compute_ack(self.last_ack, recv_seqs);
            self.last_ack = ack;
            Some((ack, selective_ack))
        }
    }
}

impl SendWindow {
    pub(super) fn new(size_limit: usize, seq: u16) -> Self {
        Self {
            used: 0,
            size_seq: None,
            size: 0,
            size_limit,
            seq,
            inflights: VecDeque::new(),
            last_num_acks: None,
            rtt: Rtt::new(),
            eof: false,
        }
    }

    pub(super) fn is_completed(&self) -> bool {
        self.eof && self.inflights.is_empty()
    }

    pub(super) fn close(&mut self) {
        self.eof = true;
    }

    pub(super) fn set_size(&mut self, seq: u16, size: usize) -> bool {
        if let Some(size_seq) = self.size_seq {
            if measure(size_seq, seq) < 0 {
                return false;
            }
        }
        self.size_seq = Some(seq);
        self.size = size;
        true
    }

    pub(super) fn set_size_limit(&mut self, size_limit: usize) {
        self.size_limit = size_limit;
    }

    // TODO: Should we include the size of the packet header and the extension when deciding
    // whether the send window has enough space?
    pub(super) fn reserve(&self, payload_size: usize) -> usize {
        cmp::min(
            payload_size,
            cmp::min(self.size, self.size_limit).saturating_sub(self.used),
        )
    }

    pub(super) fn check_ack(
        &self,
        ack: u16,
        selective_ack: &Option<SelectiveAck>,
    ) -> Result<(), Error> {
        // Regardless of the type of packet we receive, its ack should not exceed our seq.
        ensure!(
            measure(ack, self.seq) >= 0,
            AckExceedSeqSnafu { ack, seq: self.seq },
        );
        if let Some(SelectiveAck(bitmask)) = selective_ack {
            for ack_i in iter_bitmask(bitmask, ack) {
                ensure!(
                    measure(ack_i, self.seq) >= 0,
                    AckExceedSeqSnafu {
                        ack: ack_i,
                        seq: self.seq,
                    },
                );
            }
        }
        Ok(())
    }

    pub(super) fn seqs(&self) -> impl Iterator<Item = u16> + '_ {
        self.inflights.iter().map(|inflight| inflight.seq)
    }

    fn search(&self, seq: u16) -> Option<usize> {
        let seq0 = self.inflights.front().map(|inflight| inflight.seq)?;
        let d = measure(seq0, seq);
        self.inflights
            .binary_search_by_key(&d, |inflight| measure(seq0, inflight.seq))
            .ok()
    }

    pub(super) fn get(&mut self, seq: u16) -> Option<&Inflight> {
        self.search(seq).map(|i| &self.inflights[i])
    }

    pub(super) fn get_mut(&mut self, seq: u16) -> Option<&mut Inflight> {
        self.search(seq).map(|i| &mut self.inflights[i])
    }

    // Externally, this should only be called by `State::make_finish_packet`.
    pub(super) fn next_seq(&mut self) -> u16 {
        let seq = self.seq;
        self.seq = self.seq.wrapping_add(1);
        seq
    }

    pub(super) fn push(&mut self, payload: Bytes) -> u16 {
        assert!(!self.eof);
        let seq = self.next_seq();
        self.used += payload.len();
        self.inflights.push_back(Inflight::new(seq, payload));
        seq
    }

    pub(super) fn recv_ack(
        &mut self,
        ack: u16,
        selective_ack: &Option<SelectiveAck>,
        recv_at: Timestamp,
    ) {
        let seq0 = match self.inflights.front() {
            Some(inflight) => inflight.seq,
            None => return,
        };
        let d_ack = measure(seq0, ack);
        for inflight in self.inflights.iter_mut() {
            if measure(seq0, inflight.seq) <= d_ack {
                inflight.num_acks += 1;
                if inflight.num_acks == 1 && inflight.num_resends == 0 {
                    self.rtt.update(recv_at - inflight.send_at);
                }
            } else {
                break;
            }
        }

        if let Some(SelectiveAck(bitmask)) = selective_ack {
            for ack_i in iter_bitmask(bitmask, ack) {
                let mut rtt = None;
                match self.get_mut(ack_i) {
                    Some(inflight) => {
                        inflight.num_acks += 1;
                        if inflight.num_acks == 1 && inflight.num_resends == 0 {
                            rtt = Some(recv_at - inflight.send_at);
                        }
                    }
                    None => {
                        tracing::debug!(ack = ack_i, "receive selective ack of non-existent seq");
                    }
                }
                if let Some(rtt) = rtt {
                    self.rtt.update(rtt);
                }
            }
        }
    }

    pub(super) fn is_packet_lost(&self, seq: u16) -> bool {
        const NUM_DUPLICATED_ACKS: usize = 3;
        const NUM_ACKS_PAST: usize = 3;

        let i = match self.search(seq) {
            Some(i) => i,
            None => return false,
        };

        if self.inflights[i].num_acks > 0 {
            return false;
        }

        if i == 0 {
            if let Some((last_seq, last_num_acks)) = self.last_num_acks {
                assert!(
                    measure(last_seq, seq) == 1,
                    "expect no holes in seq: last_seq={} seq={}",
                    last_seq,
                    seq,
                );
                if last_num_acks >= NUM_DUPLICATED_ACKS {
                    return true;
                }
            }
        } else if self.inflights[i - 1].num_acks >= NUM_DUPLICATED_ACKS {
            return true;
        }

        let mut num_acks_past = 0;
        for inflight in self.inflights.range(i + 1..) {
            if inflight.num_acks > 0 {
                num_acks_past += 1;
                if num_acks_past >= NUM_ACKS_PAST {
                    return true;
                }
            }
        }

        false
    }

    pub(super) fn remove(&mut self) -> bool {
        if let Some(front) = self.inflights.front() {
            if front.num_acks > 0 {
                self.used -= front.payload.len();
                self.last_num_acks = Some((front.seq, front.num_acks));
                self.inflights.pop_front();
                return true;
            }
        }
        false
    }
}

impl Inflight {
    fn new(seq: u16, payload: Bytes) -> Self {
        Self {
            seq,
            payload,
            // TODO: This is not the exact time when the packet is sent, but it should be close
            // enough for now.
            send_at: timestamp::now(),
            num_resends: 0,
            num_acks: 0,
        }
    }

    pub(super) fn set_send_at(&mut self, send_at: Timestamp) {
        self.send_at = send_at;
    }

    pub(super) fn increment_resend(&mut self) {
        self.num_resends += 1;
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl RecvWindow {
        pub(crate) fn in_order_seq(&self) -> u16 {
            self.in_order_seq
        }
    }

    impl SendWindow {
        pub(crate) fn size(&self) -> usize {
            self.size
        }

        pub(crate) fn inflights(&self) -> &VecDeque<Inflight> {
            &self.inflights
        }
    }
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use hex_literal::hex;

    use super::*;

    fn assert_recv_window(window: &RecvWindow, expect: &[Option<u16>]) {
        assert_eq!(
            window
                .packets
                .iter()
                .map(|packet| packet.as_ref().map(|(seq, _)| *seq))
                .collect::<Vec<_>>(),
            expect,
        );
    }

    fn assert_recv_seqs(window: &RecvWindow, expect: &[u16]) {
        let mut recv_seqs = window.recv_seqs.iter().copied().collect::<Vec<_>>();
        recv_seqs.sort();
        assert_eq!(recv_seqs, expect);
    }

    fn assert_send_window(window: &SendWindow, expect: &[(u16, usize)]) {
        assert_eq!(
            window
                .inflights
                .iter()
                .map(|inflight| (inflight.seq, inflight.num_acks))
                .collect::<Vec<_>>(),
            expect,
        );
    }

    #[test]
    fn test_measure() {
        fn test(p: u16, q: u16, d: i32) {
            assert_eq!(measure(p, q), d);
            assert_eq!(measure(q, p), -d);
        }

        test(0, 0, 0);
        test(1, 2, 1);
        test(2, 4, 2);
        test(3, 6, 3);
        test(1000, 2000, 1000);

        test(0, u16::MAX, -1);
        test(1, u16::MAX, -2);
        test(2, u16::MAX, -3);
        test(0, u16::MAX - 1, -2);
        test(1, u16::MAX - 2, -4);

        test(u16::MAX, u16::MAX, 0);
        test(u16::MAX - 1, u16::MAX, 1);
        test(u16::MAX - 2, u16::MAX, 2);
    }

    #[test]
    fn test_compute_ack() {
        assert_eq!(compute_ack(10, HashSet::new()), (10, None));
        assert_eq!(compute_ack(10, HashSet::from([11])), (11, None));
        assert_eq!(compute_ack(10, HashSet::from([11, 12])), (12, None));
        assert_eq!(compute_ack(10, HashSet::from([8, 11, 12])), (12, None));
        assert_eq!(
            compute_ack(10, HashSet::from([9, 10, 11, 12, 13])),
            (13, None),
        );

        assert_eq!(
            compute_ack(10, HashSet::from([8, 9, 10, 12])),
            (
                10,
                Some(SelectiveAck(Bytes::from_static(&hex!("01 00 00 00")))),
            ),
        );
        assert_eq!(
            compute_ack(10, HashSet::from([7, 8, 9, 13, 20, 21, 27, 44])),
            (
                10,
                Some(SelectiveAck(Bytes::from_static(&hex!(
                    "02 83 00 00 01 00 00 00"
                )))),
            ),
        );

        assert_eq!(
            compute_ack(10, HashSet::from([11, 13])),
            (
                11,
                Some(SelectiveAck(Bytes::from_static(&hex!("01 00 00 00")))),
            ),
        );
        assert_eq!(
            compute_ack(10, HashSet::from([11, 14])),
            (
                11,
                Some(SelectiveAck(Bytes::from_static(&hex!("02 00 00 00")))),
            ),
        );
    }

    #[test]
    fn test_compute_ack_wraparound() {
        assert_eq!(compute_ack(u16::MAX, HashSet::from([0])), (0, None));
        assert_eq!(compute_ack(u16::MAX, HashSet::from([0, 1])), (1, None));

        assert_eq!(
            compute_ack(u16::MAX - 1, HashSet::from([u16::MAX, 0, 1])),
            (1, None),
        );

        assert_eq!(
            compute_ack(u16::MAX - 1, HashSet::from([0])),
            (
                u16::MAX - 1,
                Some(SelectiveAck(Bytes::from_static(&hex!("01 00 00 00")))),
            ),
        );
        assert_eq!(
            compute_ack(u16::MAX - 1, HashSet::from([1, 7, 32])),
            (
                u16::MAX - 1,
                Some(SelectiveAck(Bytes::from_static(&hex!(
                    "82 00 00 00 01 00 00 00"
                )))),
            ),
        );

        assert_eq!(
            compute_ack(u16::MAX - 2, HashSet::from([u16::MAX, 0, 1])),
            (
                u16::MAX - 2,
                Some(SelectiveAck(Bytes::from_static(&hex!("07 00 00 00")))),
            )
        );
    }

    #[test]
    fn recv_window_is_completed() {
        let mut window = RecvWindow::new(0, 100);
        assert_eq!(window.is_completed(), false);

        assert_eq!(window.close(102), Ok(()));
        assert_eq!(window.is_completed(), false);

        assert_eq!(window.recv(101, Bytes::new()), Ok(true));
        assert_eq!(window.next(), Some((101, Bytes::new())));
        assert_eq!(window.is_completed(), true);
    }

    #[test]
    fn check_state_packet_seq() {
        let mut window = RecvWindow::new(0, 100);
        assert_eq!(window.check_state_packet_seq(10), Ok(()));
        assert_eq!(window.check_state_packet_seq(11), Ok(()));
        assert_eq!(window.check_state_packet_seq(12), Ok(()));
        assert_eq!(window.check_state_packet_seq(13), Ok(()));

        assert_eq!(window.close(11), Ok(()));
        assert_eq!(window.check_state_packet_seq(10), Ok(()));
        assert_eq!(window.check_state_packet_seq(11), Ok(()));
        assert_eq!(window.check_state_packet_seq(12), Ok(()));
        assert_eq!(
            window.check_state_packet_seq(13),
            Err(Error::SeqExceedEof { seq: 13, eof: 11 }),
        );
    }

    #[test]
    fn recv() {
        let mut window = RecvWindow::new(0, 100);
        assert_recv_window(&window, &[]);
        assert_recv_seqs(&window, &[]);

        assert_eq!(
            window.recv(0, Bytes::new()),
            Err(Error::DistantSeq {
                seq: 0,
                in_order_seq: 100,
            }),
        );
        assert_recv_window(&window, &[]);
        assert_recv_seqs(&window, &[]);
        assert_eq!(
            window.recv(200, Bytes::new()),
            Err(Error::DistantSeq {
                seq: 200,
                in_order_seq: 100,
            }),
        );
        assert_recv_window(&window, &[]);
        assert_recv_seqs(&window, &[]);

        assert_eq!(window.recv(99, Bytes::new()), Ok(false));
        assert_recv_window(&window, &[]);
        assert_recv_seqs(&window, &[99]);
        assert_eq!(window.recv(100, Bytes::new()), Ok(false));
        assert_recv_window(&window, &[]);
        assert_recv_seqs(&window, &[99, 100]);

        assert_eq!(window.recv(101, Bytes::new()), Ok(true));
        assert_recv_window(&window, &[Some(101)]);
        assert_recv_seqs(&window, &[99, 100, 101]);
        assert_eq!(window.recv(101, Bytes::new()), Ok(false));
        assert_recv_window(&window, &[Some(101)]);
        assert_recv_seqs(&window, &[99, 100, 101]);

        assert_eq!(window.recv(102, Bytes::new()), Ok(true));
        assert_recv_window(&window, &[Some(101), Some(102)]);
        assert_recv_seqs(&window, &[99, 100, 101, 102]);

        assert_eq!(window.recv(105, Bytes::new()), Ok(true));
        assert_recv_window(&window, &[Some(101), Some(102), None, None, Some(105)]);
        assert_recv_seqs(&window, &[99, 100, 101, 102, 105]);

        assert_eq!(window.recv(103, Bytes::new()), Ok(true));
        assert_recv_window(&window, &[Some(101), Some(102), Some(103), None, Some(105)]);
        assert_recv_seqs(&window, &[99, 100, 101, 102, 103, 105]);

        assert_eq!(window.recv(104, Bytes::new()), Ok(true));
        assert_recv_window(
            &window,
            &[Some(101), Some(102), Some(103), Some(104), Some(105)],
        );
        assert_recv_seqs(&window, &[99, 100, 101, 102, 103, 104, 105]);
    }

    #[test]
    fn recv_wraparound() {
        let mut window = RecvWindow::new(0, u16::MAX - 2);
        assert_eq!(window.recv(u16::MAX, Bytes::new()), Ok(true));
        assert_recv_window(&window, &[None, Some(u16::MAX)]);
        assert_eq!(window.recv(0, Bytes::new()), Ok(true));
        assert_recv_window(&window, &[None, Some(u16::MAX), Some(0)]);
        assert_eq!(window.recv(2, Bytes::new()), Ok(true));
        assert_recv_window(&window, &[None, Some(u16::MAX), Some(0), None, Some(2)]);
    }

    #[test]
    fn recv_eof() {
        let mut window = RecvWindow::new(0, u16::MAX - 1);
        assert_eq!(window.close(1), Ok(()));

        assert_eq!(
            window.recv(1, Bytes::new()),
            Err(Error::SeqExceedEof { seq: 1, eof: 1 }),
        );
        assert_eq!(
            window.recv(2, Bytes::new()),
            Err(Error::SeqExceedEof { seq: 2, eof: 1 }),
        );
        assert_recv_window(&window, &[]);
        assert_recv_seqs(&window, &[]);

        assert_eq!(window.recv(0, Bytes::new()), Ok(true));
        assert_recv_window(&window, &[None, Some(0)]);
        assert_recv_seqs(&window, &[0]);

        assert_eq!(window.recv(u16::MAX, Bytes::new()), Ok(true));
        assert_recv_window(&window, &[Some(u16::MAX), Some(0)]);
        assert_recv_seqs(&window, &[0, u16::MAX]);

        assert_eq!(window.close(1), Ok(()));

        assert_eq!(window.close(2), Err(Error::DifferentEof { old: 1, new: 2 }));
    }

    #[test]
    fn recv_window_size() {
        let mut window = RecvWindow::new(0, 100);
        assert_eq!(window.size, 0);
        assert_eq!(window.size(), 0);

        assert_eq!(window.recv(100, Bytes::from_static(b"x")), Ok(false));
        assert_eq!(window.size, 0);
        assert_eq!(window.size(), 0);

        assert_eq!(window.recv(101, Bytes::from_static(b"egg")), Ok(true));
        assert_eq!(window.size, -3);
        assert_eq!(window.size(), 0);
        assert_eq!(window.recv(101, Bytes::from_static(b"x")), Ok(false));
        assert_eq!(window.size, -3);
        assert_eq!(window.size(), 0);

        assert_eq!(window.recv(103, Bytes::from_static(b"spam")), Ok(true));
        assert_eq!(window.size, -7);
        assert_eq!(window.size(), 0);

        assert_eq!(window.next(), Some((101, Bytes::from_static(b"egg"))));
        assert_eq!(window.size, -4);
        assert_eq!(window.size(), 0);

        assert_eq!(window.next(), None);
        assert_eq!(window.size, -4);
        assert_eq!(window.size(), 0);

        let mut window = RecvWindow::new(10, 100);
        assert_eq!(window.size, 10);
        assert_eq!(window.size(), 10);

        assert_eq!(window.recv(103, Bytes::from_static(b"spam")), Ok(true));
        assert_eq!(window.size, 6);
        assert_eq!(window.size(), 6);
    }

    #[test]
    fn next() {
        let mut window = RecvWindow::new(0, 100);
        assert_eq!(window.in_order_seq, 100);

        assert_eq!(window.next(), None);
        assert_recv_window(&window, &[]);
        assert_eq!(window.in_order_seq, 100);

        assert_eq!(window.recv(101, Bytes::new()), Ok(true));
        assert_eq!(window.recv(103, Bytes::new()), Ok(true));
        assert_recv_window(&window, &[Some(101), None, Some(103)]);
        assert_eq!(window.in_order_seq, 100);

        assert_eq!(window.next(), Some((101, Bytes::new())));
        assert_recv_window(&window, &[None, Some(103)]);
        assert_eq!(window.in_order_seq, 101);

        assert_eq!(window.next(), None);
        assert_recv_window(&window, &[None, Some(103)]);
        assert_eq!(window.in_order_seq, 101);

        assert_eq!(window.recv(105, Bytes::new()), Ok(true));
        assert_recv_window(&window, &[None, Some(103), None, Some(105)]);
        assert_eq!(window.in_order_seq, 101);

        assert_eq!(window.recv(102, Bytes::new()), Ok(true));
        assert_recv_window(&window, &[Some(102), Some(103), None, Some(105)]);
        assert_eq!(window.in_order_seq, 101);

        assert_eq!(window.next(), Some((102, Bytes::new())));
        assert_recv_window(&window, &[Some(103), None, Some(105)]);
        assert_eq!(window.in_order_seq, 102);
        assert_eq!(window.next(), Some((103, Bytes::new())));
        assert_recv_window(&window, &[None, Some(105)]);
        assert_eq!(window.in_order_seq, 103);
        assert_eq!(window.next(), None);
        assert_recv_window(&window, &[None, Some(105)]);
        assert_eq!(window.in_order_seq, 103);
    }

    #[test]
    fn next_wraparound() {
        let mut window = RecvWindow::new(0, u16::MAX - 1);
        assert_eq!(window.recv(u16::MAX, Bytes::new()), Ok(true));
        assert_eq!(window.recv(0, Bytes::new()), Ok(true));
        assert_eq!(window.recv(1, Bytes::new()), Ok(true));
        assert_recv_window(&window, &[Some(u16::MAX), Some(0), Some(1)]);
        assert_eq!(window.in_order_seq, u16::MAX - 1);

        assert_eq!(window.next(), Some((u16::MAX, Bytes::new())));
        assert_recv_window(&window, &[Some(0), Some(1)]);
        assert_eq!(window.in_order_seq, u16::MAX);

        assert_eq!(window.next(), Some((0, Bytes::new())));
        assert_recv_window(&window, &[Some(1)]);
        assert_eq!(window.in_order_seq, 0);
    }

    #[test]
    fn next_ack() {
        let mut window = RecvWindow::new(0, 100);
        assert_eq!(window.recv(101, Bytes::new()), Ok(true));
        assert_eq!(window.recv(102, Bytes::new()), Ok(true));
        assert_eq!(window.recv(104, Bytes::new()), Ok(true));
        assert_eq!(window.last_ack, 100);
        assert_recv_seqs(&window, &[101, 102, 104]);

        assert_eq!(
            window.next_ack(),
            Some((
                102,
                Some(SelectiveAck(Bytes::from_static(&hex!("01 00 00 00")))),
            )),
        );
        assert_eq!(window.last_ack, 102);
        assert_recv_seqs(&window, &[]);

        assert_eq!(window.next_ack(), None);
    }

    #[test]
    fn send_window_is_completed() {
        let mut window = SendWindow::new(0, 0);
        assert_eq!(window.is_completed(), false);

        assert_eq!(window.push(Bytes::new()), 0);
        assert_eq!(window.is_completed(), false);

        window.close();
        assert_eq!(window.is_completed(), false);

        window.recv_ack(0, &None, timestamp::now());
        assert_eq!(window.is_completed(), false);

        assert_eq!(window.remove(), true);
        assert_eq!(window.is_completed(), true);
    }

    #[test]
    fn set_size() {
        let mut window = SendWindow::new(0, 0);
        assert_eq!(window.size_seq, None);
        assert_eq!(window.size, 0);

        assert_eq!(window.set_size(100, 10), true);
        assert_eq!(window.size_seq, Some(100));
        assert_eq!(window.size, 10);

        assert_eq!(window.set_size(99, 10), false);
        assert_eq!(window.size_seq, Some(100));
        assert_eq!(window.size, 10);

        assert_eq!(window.set_size(100, 10), true);
        assert_eq!(window.size_seq, Some(100));
        assert_eq!(window.size, 10);

        assert_eq!(window.set_size(100, 11), true);
        assert_eq!(window.size_seq, Some(100));
        assert_eq!(window.size, 11);

        assert_eq!(window.set_size(101, 9), true);
        assert_eq!(window.size_seq, Some(101));
        assert_eq!(window.size, 9);
    }

    #[test]
    fn reserve() {
        let mut window = SendWindow::new(20, 0);
        window.set_size(0, 10);
        assert_eq!(window.reserve(0), 0);
        assert_eq!(window.reserve(1), 1);
        assert_eq!(window.reserve(9), 9);
        assert_eq!(window.reserve(10), 10);
        assert_eq!(window.reserve(11), 10);
        assert_eq!(window.reserve(12), 10);
    }

    #[test]
    fn check_ack() {
        let window = SendWindow::new(0, 0);
        assert_eq!(window.seq, 0);

        assert_eq!(window.check_ack(u16::MAX - 1, &None), Ok(()));
        assert_eq!(window.check_ack(u16::MAX, &None), Ok(()));
        assert_eq!(window.check_ack(0, &None), Ok(()));
        assert_eq!(
            window.check_ack(1, &None),
            Err(Error::AckExceedSeq { ack: 1, seq: 0 }),
        );
        assert_eq!(
            window.check_ack(2, &None),
            Err(Error::AckExceedSeq { ack: 2, seq: 0 }),
        );

        assert_eq!(
            window.check_ack(
                u16::MAX - 1,
                &Some(SelectiveAck(vec![0x01, 0x00, 0x00, 0x00].into())),
            ),
            Ok(()),
        );
        assert_eq!(
            window.check_ack(
                u16::MAX,
                &Some(SelectiveAck(vec![0x01, 0x00, 0x00, 0x00].into())),
            ),
            Err(Error::AckExceedSeq { ack: 1, seq: 0 }),
        );
        assert_eq!(
            window.check_ack(
                u16::MAX,
                &Some(SelectiveAck(vec![0x02, 0x00, 0x00, 0x00].into())),
            ),
            Err(Error::AckExceedSeq { ack: 2, seq: 0 }),
        );
    }

    #[test]
    fn search() {
        let mut window = SendWindow::new(0, u16::MAX - 2);

        assert_eq!(window.search(u16::MAX - 2), None);
        assert_eq!(window.search(u16::MAX - 1), None);

        assert_eq!(window.push(Bytes::new()), u16::MAX - 2);
        assert_eq!(window.push(Bytes::new()), u16::MAX - 1);
        assert_eq!(window.push(Bytes::new()), u16::MAX);
        assert_eq!(window.push(Bytes::new()), 0);
        assert_eq!(window.push(Bytes::new()), 1);
        assert_eq!(window.push(Bytes::new()), 2);
        assert_send_window(
            &window,
            &[
                (u16::MAX - 2, 0),
                (u16::MAX - 1, 0),
                (u16::MAX, 0),
                (0, 0),
                (1, 0),
                (2, 0),
            ],
        );

        assert_eq!(window.search(u16::MAX - 3), None);
        assert_eq!(window.search(u16::MAX - 2), Some(0));
        assert_eq!(window.search(u16::MAX - 1), Some(1));
        assert_eq!(window.search(u16::MAX), Some(2));
        assert_eq!(window.search(0), Some(3));
        assert_eq!(window.search(1), Some(4));
        assert_eq!(window.search(2), Some(5));
        assert_eq!(window.search(3), None);
    }

    #[test]
    fn push() {
        let mut window = SendWindow::new(0, 0);
        assert_send_window(&window, &[]);
        assert_eq!(window.seq, 0);
        assert_eq!(window.used, 0);

        assert_eq!(window.push(Bytes::from_static(b"spam")), 0);
        assert_send_window(&window, &[(0, 0)]);
        assert_eq!(window.seq, 1);
        assert_eq!(window.used, 4);

        assert_eq!(window.push(Bytes::from_static(b"egg")), 1);
        assert_send_window(&window, &[(0, 0), (1, 0)]);
        assert_eq!(window.seq, 2);
        assert_eq!(window.used, 7);
    }

    #[test]
    fn push_wraparound() {
        let mut window = SendWindow::new(0, u16::MAX);
        assert_send_window(&window, &[]);
        assert_eq!(window.seq, u16::MAX);

        assert_eq!(window.push(Bytes::new()), u16::MAX);
        assert_send_window(&window, &[(u16::MAX, 0)]);
        assert_eq!(window.seq, 0);

        assert_eq!(window.push(Bytes::new()), 0);
        assert_send_window(&window, &[(u16::MAX, 0), (0, 0)]);
        assert_eq!(window.seq, 1);

        assert_eq!(window.push(Bytes::new()), 1);
        assert_send_window(&window, &[(u16::MAX, 0), (0, 0), (1, 0)]);
        assert_eq!(window.seq, 2);
    }

    #[test]
    fn recv_ack() {
        let mut window = SendWindow::new(0, 10);
        assert_send_window(&window, &[]);
        window.recv_ack(
            8,
            &Some(SelectiveAck(vec![0x01, 0x00, 0x00, 0x00].into())),
            timestamp::now(),
        );
        assert_send_window(&window, &[]);

        let mut window = SendWindow::new(0, 10);
        let mut expect = vec![(10, 0), (11, 0), (12, 0)];
        assert_eq!(window.push(Bytes::new()), 10);
        assert_eq!(window.push(Bytes::new()), 11);
        assert_eq!(window.push(Bytes::new()), 12);
        assert_send_window(&window, &expect);

        window.recv_ack(9, &None, timestamp::now());
        assert_send_window(&window, &expect);

        window.recv_ack(11, &None, timestamp::now());
        expect[0].1 += 1;
        expect[1].1 += 1;
        assert_send_window(&window, &expect);

        window.recv_ack(13, &None, timestamp::now());
        expect[0].1 += 1;
        expect[1].1 += 1;
        expect[2].1 += 1;
        assert_send_window(&window, &expect);

        window.recv_ack(
            8,
            &Some(SelectiveAck(vec![0x01, 0x00, 0x00, 0x00].into())),
            timestamp::now(),
        );
        expect[0].1 += 1;
        assert_send_window(&window, &expect);

        window.recv_ack(
            8,
            &Some(SelectiveAck(vec![0x04, 0x00, 0x00, 0x00].into())),
            timestamp::now(),
        );
        expect[2].1 += 1;
        assert_send_window(&window, &expect);

        window.recv_ack(
            8,
            &Some(SelectiveAck(vec![0x08, 0x00, 0x00, 0x00].into())),
            timestamp::now(),
        );
        assert_send_window(&window, &expect);
    }

    #[test]
    fn recv_ack_wraparound() {
        let mut window = SendWindow::new(0, u16::MAX);
        let mut expect = vec![(u16::MAX, 0), (0, 0), (1, 0)];
        assert_eq!(window.push(Bytes::new()), u16::MAX);
        assert_eq!(window.push(Bytes::new()), 0);
        assert_eq!(window.push(Bytes::new()), 1);
        assert_send_window(&window, &expect);

        window.recv_ack(u16::MAX - 1, &None, timestamp::now());
        assert_send_window(&window, &expect);

        window.recv_ack(u16::MAX, &None, timestamp::now());
        expect[0].1 += 1;
        assert_send_window(&window, &expect);

        window.recv_ack(0, &None, timestamp::now());
        expect[0].1 += 1;
        expect[1].1 += 1;
        assert_send_window(&window, &expect);

        window.recv_ack(1, &None, timestamp::now());
        expect[0].1 += 1;
        expect[1].1 += 1;
        expect[2].1 += 1;
        assert_send_window(&window, &expect);

        window.recv_ack(
            u16::MAX - 2,
            &Some(SelectiveAck(vec![0x01, 0x00, 0x00, 0x00].into())),
            timestamp::now(),
        );
        expect[0].1 += 1;
        assert_send_window(&window, &expect);

        window.recv_ack(
            u16::MAX - 1,
            &Some(SelectiveAck(vec![0x01, 0x00, 0x00, 0x00].into())),
            timestamp::now(),
        );
        expect[1].1 += 1;
        assert_send_window(&window, &expect);
    }

    #[test]
    fn recv_ack_rtt_update() {
        let mut window = SendWindow::new(0, 0);
        assert_eq!(window.push(Bytes::new()), 0);
        assert_eq!(window.push(Bytes::new()), 1);
        assert_eq!(window.push(Bytes::new()), 2);
        assert_eq!(window.push(Bytes::new()), 3);

        window.inflights[0].send_at = Timestamp::ZERO;
        window.inflights[1].send_at = Timestamp::ZERO;
        window.inflights[2].send_at = Timestamp::ZERO;
        window.inflights[3].send_at = Timestamp::ZERO;

        window.inflights[1].num_resends = 1;
        window.inflights[3].num_resends = 1;

        assert_eq!(window.rtt.average, Duration::ZERO);
        assert_eq!(window.rtt.variance, Duration::ZERO);
        for i in 1..=3 {
            window.recv_ack(1, &None, Timestamp::from_secs(4));
            assert_send_window(&window, &[(0, i), (1, i), (2, 0), (3, 0)]);
            assert_eq!(window.rtt.variance, Duration::from_secs(1));
        }

        window.rtt.average = Duration::ZERO;
        window.rtt.variance = Duration::ZERO;
        for i in 1..=3 {
            window.recv_ack(
                0,
                &Some(SelectiveAck(vec![0x03, 0x00, 0x00, 0x00].into())),
                Timestamp::from_secs(4),
            );
            assert_send_window(&window, &[(0, 3 + i), (1, 3), (2, i), (3, i)]);
            assert_eq!(window.rtt.variance, Duration::from_secs(1));
        }
    }

    #[test]
    fn is_packet_lost() {
        let window = SendWindow::new(0, 10);
        assert_eq!(window.is_packet_lost(10), false);

        let mut window = SendWindow::new(0, u16::MAX - 1);
        assert_eq!(window.push(Bytes::new()), u16::MAX - 1);
        assert_eq!(window.push(Bytes::new()), u16::MAX);
        assert_eq!(window.push(Bytes::new()), 0);
        assert_eq!(window.push(Bytes::new()), 1);
        assert_eq!(window.push(Bytes::new()), 2);

        assert_eq!(window.is_packet_lost(3), false);

        //
        // Test the `NUM_ACKS_PAST` rule.
        //

        assert_eq!(window.is_packet_lost(u16::MAX - 1), false);
        window.inflights[2].num_acks = 1;
        assert_eq!(window.is_packet_lost(u16::MAX - 1), false);
        window.inflights[3].num_acks = 1;
        assert_eq!(window.is_packet_lost(u16::MAX - 1), false);
        window.inflights[4].num_acks = 1;
        assert_eq!(window.is_packet_lost(u16::MAX - 1), true);

        window.inflights[0].num_acks = 1;
        assert_eq!(window.is_packet_lost(u16::MAX - 1), false);

        //
        // Test the `NUM_DUPLICATED_ACKS` rule.
        //

        let mut window = SendWindow::new(0, u16::MAX);
        assert_eq!(window.push(Bytes::new()), u16::MAX);
        assert_eq!(window.push(Bytes::new()), 0);
        assert_send_window(&window, &[(u16::MAX, 0), (0, 0)]);
        assert_eq!(window.last_num_acks, None);

        assert_eq!(window.is_packet_lost(0), false);

        window.inflights[0].num_acks = 3;
        assert_send_window(&window, &[(u16::MAX, 3), (0, 0)]);
        assert_eq!(window.is_packet_lost(0), true);

        assert_eq!(window.remove(), true);
        assert_send_window(&window, &[(0, 0)]);
        assert_eq!(window.last_num_acks, Some((u16::MAX, 3)));
        assert_eq!(window.is_packet_lost(0), true);
    }

    #[test]
    fn remove() {
        let mut window = SendWindow::new(0, 10);
        assert_eq!(window.used, 0);
        assert_eq!(window.last_num_acks, None);

        assert_eq!(window.remove(), false);
        assert_eq!(window.used, 0);
        assert_eq!(window.last_num_acks, None);

        assert_eq!(window.push(Bytes::from_static(b"spam")), 10);
        assert_send_window(&window, &[(10, 0)]);
        assert_eq!(window.used, 4);
        assert_eq!(window.last_num_acks, None);

        assert_eq!(window.remove(), false);
        assert_send_window(&window, &[(10, 0)]);
        assert_eq!(window.used, 4);
        assert_eq!(window.last_num_acks, None);

        window.inflights[0].num_acks = 1;
        assert_send_window(&window, &[(10, 1)]);

        assert_eq!(window.remove(), true);
        assert_send_window(&window, &[]);
        assert_eq!(window.used, 0);
        assert_eq!(window.last_num_acks, Some((10, 1)));

        let mut window = SendWindow::new(0, 10);
        assert_eq!(window.push(Bytes::from_static(b"spam")), 10);
        assert_eq!(window.push(Bytes::from_static(b"egg")), 11);
        window.inflights[0].num_acks = 2;
        window.inflights[1].num_acks = 3;
        assert_send_window(&window, &[(10, 2), (11, 3)]);
        assert_eq!(window.used, 7);
        assert_eq!(window.last_num_acks, None);

        assert_eq!(window.remove(), true);
        assert_send_window(&window, &[(11, 3)]);
        assert_eq!(window.used, 3);
        assert_eq!(window.last_num_acks, Some((10, 2)));

        assert_eq!(window.remove(), true);
        assert_send_window(&window, &[]);
        assert_eq!(window.used, 0);
        assert_eq!(window.last_num_acks, Some((11, 3)));
    }
}
