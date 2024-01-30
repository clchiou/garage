use std::collections::HashMap;
use std::sync::{
    atomic::{AtomicU64, Ordering},
    Arc,
};

use bittorrent_manager::Endpoint;

#[derive(Clone, Debug)]
pub struct Torrent(Arc<TorrentInner>);

#[derive(Debug)]
pub(crate) struct TorrentInner {
    pub(crate) send: Accumulator,
    pub(crate) recv: Accumulator,
    pub(crate) have: Accumulator,
    size: u64,
}

#[derive(Debug)]
pub(crate) struct Accumulator(AtomicU64);

#[derive(Debug)]
pub(crate) struct Stats(HashMap<Endpoint, Stat>);

#[derive(Debug)]
pub(crate) struct Stat {
    /// Number of bytes we receive from this peer.
    pub(crate) recv: u64,
    /// Number of bytes sent to this peer.
    pub(crate) send: u64,
}

impl Torrent {
    pub(crate) fn new(inner: Arc<TorrentInner>) -> Self {
        Self(inner)
    }
}

impl TorrentInner {
    pub(crate) fn new(have: u64, size: u64) -> Self {
        Self {
            send: Accumulator(AtomicU64::new(0)),
            recv: Accumulator(AtomicU64::new(0)),
            have: Accumulator(AtomicU64::new(have)),
            size,
        }
    }
}

impl Accumulator {
    pub(crate) fn get(&self) -> u64 {
        self.0.load(Ordering::SeqCst)
    }

    pub(crate) fn add(&self, n: u64) {
        self.0.fetch_add(n, Ordering::SeqCst);
    }
}

impl bittorrent_tracker::Torrent for Torrent {
    fn num_bytes_send(&self) -> u64 {
        self.0.send.get()
    }

    fn num_bytes_recv(&self) -> u64 {
        self.0.recv.get()
    }

    fn num_bytes_left(&self) -> u64 {
        self.0.size.saturating_sub(self.0.have.get())
    }
}

impl Stats {
    pub(crate) fn new() -> Self {
        Self(HashMap::new())
    }

    pub(crate) fn get(&self, peer: Endpoint) -> &Stat {
        self.0.get(&peer).unwrap_or(&Stat::ZERO)
    }

    pub(crate) fn get_mut(&mut self, peer: Endpoint) -> &mut Stat {
        self.0.entry(peer).or_insert_with(Stat::new)
    }
}

impl Stat {
    const ZERO: Self = Self::new();

    const fn new() -> Self {
        Self { recv: 0, send: 0 }
    }
}

#[cfg(test)]
mod tests {
    use bittorrent_tracker::Torrent as _;

    use super::*;

    #[test]
    fn torrent() {
        let torrent = Torrent::new(Arc::new(TorrentInner::new(7, 11)));
        assert_eq!(torrent.0.have.0.load(Ordering::SeqCst), 7);
        assert_eq!(torrent.0.size, 11);

        assert_eq!(torrent.num_bytes_send(), 0);
        assert_eq!(torrent.num_bytes_recv(), 0);
        assert_eq!(torrent.num_bytes_left(), 4);

        torrent.0.send.add(1);
        torrent.0.recv.add(2);
        torrent.0.have.add(3);

        assert_eq!(torrent.num_bytes_send(), 1);
        assert_eq!(torrent.num_bytes_recv(), 2);
        assert_eq!(torrent.num_bytes_left(), 1);

        torrent.0.have.add(4);
        assert_eq!(torrent.num_bytes_left(), 0);
    }
}
