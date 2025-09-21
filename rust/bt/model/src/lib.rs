mod peer;
mod stat;

use std::collections::hash_map::Entry;
use std::collections::{BTreeMap, HashMap};
use std::net::IpAddr;
use std::sync::Arc;

use bt_base::{Bitfield, Bitslice, InfoHash, PeerEndpoint, PieceIndex};

// This is the routing table that we download from the trackers and the DHT.  For now, we keep it
// separate from the peer stats in `Model`.
pub use crate::peer::Peers;

#[derive(Debug)]
pub struct Model {
    torrents: Torrents,
    // TODO: Should we save this across process starts?
    peer_stats: PeerStats,
}

#[derive(Debug)]
pub struct Torrents(HashMap<InfoHash, Torrent>);

#[derive(Debug)]
pub struct Torrent {
    self_pieces: Bitfield,
    peer_pieces: HashMap<PeerEndpoint, Bitfield>,
    // TODO: Save this across process starts.
    stat: TorrentStat,
}

pub type TorrentStat = Arc<stat::TorrentStat>;

#[derive(Debug)]
pub struct PeerStats(HashMap<HostAddr, PeerStatsPerHost>);

// TODO: I am not sure if this is actually useful.
pub type HostAddr = IpAddr;

// Sorting peers seems nice.
#[derive(Debug)]
pub struct PeerStatsPerHost(BTreeMap<PeerEndpoint, PeerStat>);

pub type PeerStat = Arc<stat::PeerStat>;

impl Default for Model {
    fn default() -> Self {
        Self::new()
    }
}

impl Model {
    pub fn new() -> Self {
        Self {
            torrents: Torrents::new(),
            peer_stats: PeerStats::new(),
        }
    }

    pub fn torrents(&self) -> &Torrents {
        &self.torrents
    }

    pub fn torrents_mut(&mut self) -> &mut Torrents {
        &mut self.torrents
    }

    pub fn peer_stats(&self) -> &PeerStats {
        &self.peer_stats
    }

    pub fn peer_stats_mut(&mut self) -> &mut PeerStats {
        &mut self.peer_stats
    }
}

impl Torrents {
    fn new() -> Self {
        Self(HashMap::new())
    }

    pub fn iter(&self) -> impl Iterator<Item = (InfoHash, &Torrent)> {
        self.0
            .iter()
            .map(|(info_hash, torrent)| (info_hash.clone(), torrent))
    }

    pub fn get(&self, info_hash: InfoHash) -> Option<&Torrent> {
        self.0.get(&info_hash)
    }

    pub fn get_mut(&mut self, info_hash: InfoHash) -> Option<&mut Torrent> {
        self.0.get_mut(&info_hash)
    }

    pub fn insert(&mut self, info_hash: InfoHash, self_pieces: Bitfield) -> bool {
        match self.0.entry(info_hash) {
            Entry::Occupied(entry) => {
                let torrent = entry.into_mut();
                assert_eq!(torrent.self_pieces.len(), self_pieces.len());
                torrent.self_pieces = self_pieces;
                false
            }
            Entry::Vacant(entry) => {
                entry.insert(Torrent::new(self_pieces));
                true
            }
        }
    }

    pub fn remove(&mut self, info_hash: InfoHash) -> bool {
        self.0.remove(&info_hash).is_some()
    }
}

impl Torrent {
    fn new(self_pieces: Bitfield) -> Self {
        Self {
            self_pieces,
            peer_pieces: HashMap::new(),
            stat: Arc::new(stat::TorrentStat::new()),
        }
    }

    pub fn self_pieces(&self) -> &Bitslice {
        &self.self_pieces
    }

    pub fn self_pieces_mut(&mut self) -> &mut Bitfield {
        &mut self.self_pieces
    }

    pub fn peer_pieces(&self, peer_endpoint: PeerEndpoint) -> Option<&Bitslice> {
        self.peer_pieces
            .get(&peer_endpoint)
            .map(|peer_pieces| &**peer_pieces)
    }

    pub fn peer_pieces_mut(&mut self, peer_endpoint: PeerEndpoint) -> Option<&mut Bitfield> {
        self.peer_pieces.get_mut(&peer_endpoint)
    }

    pub fn peers(&self, PieceIndex(index): PieceIndex) -> impl Iterator<Item = PeerEndpoint> {
        let index = usize::try_from(index).expect("usize");
        self.peer_pieces
            .iter()
            .filter_map(move |(peer_endpoint, peer_pieces)| {
                peer_pieces[index].then_some(*peer_endpoint)
            })
    }

    pub fn insert(&mut self, peer_endpoint: PeerEndpoint, peer_pieces: Bitfield) -> bool {
        assert_eq!(self.self_pieces.len(), peer_pieces.len());
        self.peer_pieces
            .insert(peer_endpoint, peer_pieces)
            .is_none()
    }

    pub fn remove(&mut self, peer_endpoint: PeerEndpoint) -> bool {
        self.peer_pieces.remove(&peer_endpoint).is_some()
    }

    pub fn stat(&self) -> TorrentStat {
        self.stat.clone()
    }
}

impl PeerStats {
    fn new() -> Self {
        Self(HashMap::new())
    }

    pub fn get(&self, peer_endpoint: PeerEndpoint) -> Option<PeerStat> {
        self.0
            .get(&peer_endpoint.ip())
            .and_then(|per_host| per_host.get(peer_endpoint))
    }

    pub fn get_or_insert_default(&mut self, peer_endpoint: PeerEndpoint) -> PeerStat {
        self.0
            .entry(peer_endpoint.ip())
            .or_insert_with(PeerStatsPerHost::new)
            .get_or_insert_default(peer_endpoint)
    }

    pub fn peers(&self, host: HostAddr) -> Option<&PeerStatsPerHost> {
        self.0.get(&host)
    }

    pub fn remove(&mut self, peer_endpoint: PeerEndpoint) -> bool {
        match self.0.entry(peer_endpoint.ip()) {
            Entry::Occupied(mut entry) => {
                let per_host = entry.get_mut();
                let removed = per_host.remove(peer_endpoint);
                if per_host.is_empty() {
                    entry.remove();
                }
                removed
            }
            Entry::Vacant(_) => false,
        }
    }
}

impl PeerStatsPerHost {
    fn new() -> Self {
        Self(BTreeMap::new())
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn iter(&self) -> impl Iterator<Item = (PeerEndpoint, PeerStat)> {
        self.0.iter().map(|(peer, stat)| (*peer, stat.clone()))
    }

    pub fn get(&self, peer_endpoint: PeerEndpoint) -> Option<PeerStat> {
        self.0.get(&peer_endpoint).cloned()
    }

    pub fn get_or_insert_default(&mut self, peer_endpoint: PeerEndpoint) -> PeerStat {
        self.0
            .entry(peer_endpoint)
            .or_insert_with(|| Arc::new(stat::PeerStat::new()))
            .clone()
    }

    pub fn remove(&mut self, peer_endpoint: PeerEndpoint) -> bool {
        self.0.remove(&peer_endpoint).is_some()
    }
}
