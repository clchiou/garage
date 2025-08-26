use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};

use g1_base::iter::IteratorExt;
use g1_base::sync::MutexExt;

use bt_base::{InfoHash, PeerEndpoint};

#[derive(Clone, Debug)]
pub struct Peers(Arc<Mutex<PeersInner>>);

#[derive(Debug)]
struct PeersInner {
    peers: HashMap<InfoHash, HashSet<PeerEndpoint>>,
}

impl Default for Peers {
    fn default() -> Self {
        Self::new()
    }
}

impl Peers {
    pub fn new() -> Self {
        Self(Arc::new(Mutex::new(PeersInner::new())))
    }

    pub fn get_peers(&self, info_hash: InfoHash) -> Option<Vec<PeerEndpoint>> {
        self.0.must_lock().get_peers(info_hash)
    }

    pub fn insert_peers<I>(&self, info_hash: InfoHash, peers: I)
    where
        I: IntoIterator<Item = PeerEndpoint>,
    {
        self.0.must_lock().insert_peers(info_hash, peers);
    }
}

impl PeersInner {
    fn new() -> Self {
        Self {
            peers: HashMap::new(),
        }
    }

    fn get_peers(&self, info_hash: InfoHash) -> Option<Vec<PeerEndpoint>> {
        self.peers
            .get(&info_hash)
            .map(|peers| peers.iter().copied().collect_then_sort())
    }

    fn insert_peers<I>(&mut self, info_hash: InfoHash, peers: I)
    where
        I: IntoIterator<Item = PeerEndpoint>,
    {
        self.peers.entry(info_hash).or_default().extend(peers);
    }
}
