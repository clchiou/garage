#[cfg(feature = "fold")]
pub mod fold;

mod conn;
mod stat;

use std::collections::hash_map::Entry;
use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use snafu::prelude::*;
use tokio::sync::broadcast::{self, Receiver, Sender, WeakSender};

use bt_base::{Bitfield, ConnId, ConnPair, Features, InfoHash, Layout, PeerEndpoint, PieceIndex};

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("torrent removed"))]
pub struct TorrentRemoved;

// This is roughly what we expect:
//   NewTorrent
//   InitTorrent (from the metadata files)
//     NewPeer
//     ConnectPeer
//       InitTorrent (download the metadata files from peers)
//       InitPeer
//         SelfChoking/SelfInterested/PeerChoking/PeerInterested/Snubbing
//         SetSelfPiece/SetPeerPiece
//     DisconnectPeer
//     RemovePeer
//   RemoveTorrent
//
// In general, it returns `true` when it changes.  If the caller inserts/sets an identical value,
// it returns `false`.
#[derive(Debug)]
pub struct Model {
    // This is the routing table that we download from the trackers and the DHT.  In trackerless
    // mode, we connect to peers before initializing the torrent (from them, we will download the
    // metadata files).
    peers: Peers,

    conn_states: ConnStates,

    torrents: Torrents,

    // This is the only `Sender` instance; the channel will be closed when `Model` is dropped.
    sender: Sender<ModelUpdate>,
}

#[derive(Debug)]
pub struct Peers {
    peers: HashMap<InfoHash, HashSet<PeerEndpoint>>,
    model_update_send: ModelUpdateSend,
}

#[derive(Debug)]
pub struct ConnStates {
    conn_states: HashMap<InfoHash, HashMap<ConnPair, ConnState>>,
    model_update_send: ModelUpdateSend,
}

pub type ConnState = Arc<conn::ConnState>;

#[derive(Debug)]
pub struct Torrents {
    torrents: HashMap<InfoHash, Torrent>,
    model_update_send: ModelUpdateSend,
}

#[derive(Debug)]
pub struct Torrent {
    info_hash: InfoHash,

    layout: Layout,

    self_pieces: Bitfield,
    peer_pieces: HashMap<ConnPair, Bitfield>,

    // TODO: Save this across process starts.
    stat: TorrentStat,
    // TODO: Should we save this across process starts?
    peer_stats: PeerStats,

    model_update_send: ModelUpdateSend,
}

pub type TorrentStat = Arc<stat::TorrentStat>;

#[derive(Debug)]
pub struct PeerStats(HashMap<ConnPair, PeerStat>);

pub type PeerStat = Arc<stat::PeerStat>;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ModelUpdate {
    NewTorrent(InfoHash),
    InitTorrent(InfoHash),
    RemoveTorrent(InfoHash),

    //
    // `Peers` changes.
    //
    NewPeer(InfoHash, PeerEndpoint),
    // TODO: Consider adding `RemovePeer`.

    //
    // `ConnState` changes.
    //
    ConnectPeer(ConnId),
    DisconnectPeer(ConnId),

    SelfChoking(ConnId, bool),
    SelfInterested(ConnId, bool),

    PeerChoking(ConnId, bool),
    PeerInterested(ConnId, bool),

    Snubbing(ConnId, bool),

    //
    // `Torrent` changes.
    //
    InitPeer(ConnId),

    SetSelfPiece(InfoHash, PieceIndex),
    SetPeerPiece(ConnId, PieceIndex),
}

// Subscribers should handle `RecvError::Lagged`.  A straightforward approach is to scan the entire
// model.
pub type ModelUpdateRecv = Receiver<ModelUpdate>;

#[derive(Clone, Debug)]
struct ModelUpdateSend(WeakSender<ModelUpdate>);

impl ModelUpdateSend {
    fn send<F>(&self, f: F)
    where
        F: FnOnce() -> ModelUpdate,
    {
        if let Some(sender) = self.0.upgrade() {
            let _ = sender.send(f());
        }
    }
}

impl Default for Model {
    fn default() -> Self {
        Self::new()
    }
}

impl Model {
    pub fn new() -> Self {
        // The capacity should be large enough to absorb instantaneous bursts of updates.
        // TODO: Make channel capacity configurable.
        let (sender, _) = broadcast::channel(64);
        let model_update_send = ModelUpdateSend(sender.downgrade());
        Self {
            peers: Peers::new(model_update_send.clone()),
            conn_states: ConnStates::new(model_update_send.clone()),
            torrents: Torrents::new(model_update_send),
            sender,
        }
    }

    pub fn new_torrent(&mut self, info_hash: InfoHash) -> bool {
        if self.peers.insert_torrent(info_hash.clone()) {
            // The torrent should not be initialized yet at this point.
            assert!(!self.torrents.contains(info_hash.clone()));
            let _ = self.sender.send(ModelUpdate::NewTorrent(info_hash));
            true
        } else {
            false
        }
    }

    pub fn init_torrent(
        &mut self,
        info_hash: InfoHash,
        layout: Layout,
        self_pieces: Bitfield,
    ) -> bool {
        // The torrent should already be open at this point.
        assert!(self.peers.contains_torrent(info_hash.clone()));
        if self.torrents.insert(info_hash.clone(), layout, self_pieces) {
            let _ = self.sender.send(ModelUpdate::InitTorrent(info_hash));
            true
        } else {
            false
        }
    }

    pub fn remove_torrent(&mut self, info_hash: InfoHash) -> bool {
        let removed = self.torrents.remove(info_hash.clone());
        if self.peers.remove_torrent(info_hash.clone()) {
            let _ = self.sender.send(ModelUpdate::RemoveTorrent(info_hash));
            true
        } else {
            assert!(!removed);
            false
        }
    }

    pub fn connect_peer(&mut self, conn_id: ConnId, peer_features: Features) {
        if let Some(torrent) = self.torrents.get_mut(conn_id.info_hash()) {
            // The peer should not be initialized yet at this point.
            assert!(!torrent.contains(&conn_id.conn_pair));
            assert!(torrent.peer_stats.insert(conn_id.conn_pair));
        }
        // We disallow duplicate insertion, as it likely means the caller is managing the
        // connection lifetime incorrectly.
        assert!(self.conn_states.insert(conn_id, peer_features));
    }

    pub fn disconnect_peer(&mut self, conn_id: &ConnId) {
        if let Some(torrent) = self.torrents.get_mut(conn_id.info_hash()) {
            // The peer might not have initialized yet, but the peer stats must have been inserted.
            torrent.remove(&conn_id.conn_pair);
            assert!(torrent.peer_stats.remove(&conn_id.conn_pair));
        }
        // We disallow duplicate removal, as it likely means the caller is managing the connection
        // lifetime incorrectly.
        assert!(self.conn_states.remove(conn_id));
    }

    pub fn peers(&self) -> &Peers {
        &self.peers
    }

    pub fn peers_mut(&mut self) -> &mut Peers {
        &mut self.peers
    }

    pub fn conn_states(&self) -> &ConnStates {
        &self.conn_states
    }

    pub fn torrents(&self) -> &Torrents {
        &self.torrents
    }

    pub fn torrents_mut(&mut self) -> &mut Torrents {
        &mut self.torrents
    }

    pub fn subscribe(&self) -> ModelUpdateRecv {
        self.sender.subscribe()
    }
}

impl Peers {
    fn new(model_update_send: ModelUpdateSend) -> Self {
        Self {
            peers: HashMap::new(),
            model_update_send,
        }
    }

    pub fn iter(&self) -> impl Iterator<Item = (InfoHash, PeerEndpoint)> {
        self.peers.iter().flat_map(|(info_hash, peers)| {
            peers.iter().copied().map(|peer| (info_hash.clone(), peer))
        })
    }

    pub fn peers(
        &self,
        info_hash: InfoHash,
    ) -> Result<impl Iterator<Item = (InfoHash, PeerEndpoint)>, TorrentRemoved> {
        let peers = self.peers.get(&info_hash).context(TorrentRemovedSnafu)?;
        Ok(peers
            .iter()
            .copied()
            .map(move |peer| (info_hash.clone(), peer)))
    }

    pub fn contains_torrent(&self, info_hash: InfoHash) -> bool {
        self.peers.contains_key(&info_hash)
    }

    pub fn contains(&self, info_hash: InfoHash, peer_endpoint: PeerEndpoint) -> bool {
        self.peers
            .get(&info_hash)
            .is_some_and(|peers| peers.contains(&peer_endpoint))
    }

    fn insert_torrent(&mut self, info_hash: InfoHash) -> bool {
        match self.peers.entry(info_hash) {
            Entry::Occupied(_) => false,
            Entry::Vacant(entry) => {
                entry.insert(HashSet::new());
                true
            }
        }
    }

    pub fn insert(
        &mut self,
        info_hash: InfoHash,
        peer_endpoint: PeerEndpoint,
    ) -> Result<bool, TorrentRemoved> {
        let peers = self
            .peers
            .get_mut(&info_hash)
            .context(TorrentRemovedSnafu)?;
        Ok(if peers.insert(peer_endpoint) {
            self.model_update_send
                .send(|| ModelUpdate::NewPeer(info_hash, peer_endpoint));
            true
        } else {
            false
        })
    }

    fn remove_torrent(&mut self, info_hash: InfoHash) -> bool {
        self.peers.remove(&info_hash).is_some()
    }

    pub fn remove(
        &mut self,
        info_hash: InfoHash,
        peer_endpoint: PeerEndpoint,
    ) -> Result<bool, TorrentRemoved> {
        Ok(self
            .peers
            .get_mut(&info_hash)
            .context(TorrentRemovedSnafu)?
            .remove(&peer_endpoint))
    }
}

impl ConnStates {
    fn new(model_update_send: ModelUpdateSend) -> Self {
        Self {
            conn_states: HashMap::new(),
            model_update_send,
        }
    }

    pub fn iter(&self) -> impl Iterator<Item = (ConnId, ConnState)> {
        self.conn_states
            .iter()
            .flat_map(|(info_hash, conn_states)| {
                conn_states.iter().map(|(conn_pair, conn_state)| {
                    ((info_hash.clone(), *conn_pair).into(), conn_state.clone())
                })
            })
    }

    pub fn conn_states(&self, info_hash: InfoHash) -> impl Iterator<Item = (ConnId, ConnState)> {
        self.conn_states
            .get(&info_hash)
            .into_iter()
            .flat_map(move |conn_states| {
                let info_hash = info_hash.clone();
                conn_states.iter().map(move |(conn_pair, conn_state)| {
                    ((info_hash.clone(), *conn_pair).into(), conn_state.clone())
                })
            })
    }

    pub fn contains(&self, conn_id: &ConnId) -> bool {
        self.conn_states
            .get(&conn_id.info_hash)
            .is_some_and(|conn_states| conn_states.contains_key(&conn_id.conn_pair))
    }

    pub fn get(&self, conn_id: &ConnId) -> Option<ConnState> {
        self.conn_states
            .get(&conn_id.info_hash)?
            .get(&conn_id.conn_pair)
            .cloned()
    }

    fn insert(&mut self, conn_id: ConnId, peer_features: Features) -> bool {
        match self
            .conn_states
            .entry(conn_id.info_hash())
            .or_default()
            .entry(conn_id.conn_pair)
        {
            Entry::Occupied(entry) => {
                assert_eq!(entry.get().peer_features(), peer_features);
                false
            }
            Entry::Vacant(entry) => {
                entry.insert(Arc::new(conn::ConnState::new(
                    conn_id.clone(),
                    peer_features,
                    self.model_update_send.clone(),
                )));
                self.model_update_send
                    .send(|| ModelUpdate::ConnectPeer(conn_id));
                true
            }
        }
    }

    fn remove(&mut self, conn_id: &ConnId) -> bool {
        match self.conn_states.entry(conn_id.info_hash()) {
            Entry::Occupied(mut entry) => {
                let conn_states = entry.get_mut();
                let removed = conn_states.remove(&conn_id.conn_pair).is_some();
                if conn_states.is_empty() {
                    entry.remove();
                }
                if removed {
                    self.model_update_send
                        .send(|| ModelUpdate::DisconnectPeer(conn_id.clone()));
                }
                removed
            }
            Entry::Vacant(_) => false,
        }
    }
}

impl Torrents {
    fn new(model_update_send: ModelUpdateSend) -> Self {
        Self {
            torrents: HashMap::new(),
            model_update_send,
        }
    }

    pub fn iter(&self) -> impl Iterator<Item = (InfoHash, &Torrent)> {
        self.torrents
            .iter()
            .map(|(info_hash, torrent)| (info_hash.clone(), torrent))
    }

    pub fn contains(&self, info_hash: InfoHash) -> bool {
        self.torrents.contains_key(&info_hash)
    }

    pub fn get(&self, info_hash: InfoHash) -> Option<&Torrent> {
        self.torrents.get(&info_hash)
    }

    pub fn get_mut(&mut self, info_hash: InfoHash) -> Option<&mut Torrent> {
        self.torrents.get_mut(&info_hash)
    }

    fn insert(&mut self, info_hash: InfoHash, layout: Layout, self_pieces: Bitfield) -> bool {
        match self.torrents.entry(info_hash.clone()) {
            Entry::Occupied(entry) => {
                let torrent = entry.into_mut();
                assert_eq!(torrent.layout, layout);
                assert_eq!(torrent.self_pieces.len(), self_pieces.len());
                if torrent.self_pieces == self_pieces {
                    return false;
                }
                torrent.self_pieces = self_pieces;
            }
            Entry::Vacant(entry) => {
                entry.insert(Torrent::new(
                    info_hash,
                    layout,
                    self_pieces,
                    self.model_update_send.clone(),
                ));
            }
        }
        true
    }

    fn remove(&mut self, info_hash: InfoHash) -> bool {
        self.torrents.remove(&info_hash).is_some()
    }
}

impl Torrent {
    fn new(
        info_hash: InfoHash,
        layout: Layout,
        self_pieces: Bitfield,
        model_update_send: ModelUpdateSend,
    ) -> Self {
        assert_eq!(layout.num_pieces(), self_pieces.len());
        Self {
            info_hash,
            layout,
            self_pieces,
            peer_pieces: HashMap::new(),
            stat: Arc::new(stat::TorrentStat::new()),
            peer_stats: PeerStats::new(),
            model_update_send,
        }
    }

    pub fn layout(&self) -> &Layout {
        &self.layout
    }

    // We return `&Bitfield` rather than `&Bitslice`, because it exposes raw slices.
    pub fn self_pieces(&self) -> &Bitfield {
        &self.self_pieces
    }

    pub fn set_self_piece(&mut self, index: PieceIndex) -> bool {
        if self.self_pieces.replace(index.into(), true) {
            return false;
        }
        self.model_update_send
            .send(|| ModelUpdate::SetSelfPiece(self.info_hash.clone(), index));
        true
    }

    pub fn iter(&self) -> impl Iterator<Item = (&ConnPair, &Bitfield)> {
        self.peer_pieces.iter()
    }

    pub fn contains(&self, conn_pair: &ConnPair) -> bool {
        self.peer_pieces.contains_key(conn_pair)
    }

    // We return `&Bitfield` rather than `&Bitslice`, because it exposes raw slices.
    pub fn get(&self, conn_pair: &ConnPair) -> Option<&Bitfield> {
        self.peer_pieces.get(conn_pair)
    }

    pub fn insert(&mut self, conn_pair: ConnPair, peer_pieces: Bitfield) -> bool {
        assert_eq!(self.self_pieces.len(), peer_pieces.len());
        match self.peer_pieces.entry(conn_pair) {
            Entry::Occupied(entry) => {
                let peer_pieces_mut = entry.into_mut();
                if *peer_pieces_mut == peer_pieces {
                    return false;
                }
                *peer_pieces_mut = peer_pieces;
            }
            Entry::Vacant(entry) => {
                entry.insert(peer_pieces);
            }
        }
        self.model_update_send
            .send(|| ModelUpdate::InitPeer((self.info_hash.clone(), conn_pair).into()));
        true
    }

    pub fn set_peer_piece(&mut self, conn_pair: &ConnPair, index: PieceIndex) -> Option<bool> {
        let peer_pieces = self.peer_pieces.get_mut(conn_pair)?;
        if peer_pieces.replace(index.into(), true) {
            return Some(false);
        }
        self.model_update_send
            .send(|| ModelUpdate::SetPeerPiece((self.info_hash.clone(), *conn_pair).into(), index));
        Some(true)
    }

    fn remove(&mut self, conn_pair: &ConnPair) -> bool {
        self.peer_pieces.remove(conn_pair).is_some()
    }

    pub fn stat(&self) -> TorrentStat {
        self.stat.clone()
    }

    pub fn peer_stats(&self) -> &PeerStats {
        &self.peer_stats
    }
}

impl PeerStats {
    fn new() -> Self {
        Self(HashMap::new())
    }

    pub fn get(&self, conn_pair: &ConnPair) -> Option<PeerStat> {
        self.0.get(conn_pair).cloned()
    }

    fn insert(&mut self, conn_pair: ConnPair) -> bool {
        match self.0.entry(conn_pair) {
            Entry::Occupied(_) => false,
            Entry::Vacant(entry) => {
                entry.insert(Arc::new(stat::PeerStat::new()));
                true
            }
        }
    }

    fn remove(&mut self, conn_pair: &ConnPair) -> bool {
        self.0.remove(conn_pair).is_some()
    }
}
