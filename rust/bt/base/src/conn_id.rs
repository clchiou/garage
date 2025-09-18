use std::fmt::{self, Display};

use crate::info_hash::InfoHash;
use crate::peer_endpoint::PeerEndpoint;

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct ConnId {
    // A connection is uniquely identified by both endpoints.  We include the info hash merely for
    // convenience, as we and our peers may serve multiple torrents at the same endpoint.
    pub info_hash: InfoHash,
    pub conn_pair: ConnPair,
}

pub type ConnPair = (PeerEndpoint, PeerEndpoint);

impl Display for ConnId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "({}, {} -> {})",
            self.info_hash, self.conn_pair.0, self.conn_pair.1,
        )
    }
}

impl From<(InfoHash, ConnPair)> for ConnId {
    fn from((info_hash, conn_pair): (InfoHash, ConnPair)) -> Self {
        Self {
            info_hash,
            conn_pair,
        }
    }
}

impl From<(InfoHash, PeerEndpoint, PeerEndpoint)> for ConnId {
    fn from(
        (info_hash, self_endpoint, peer_endpoint): (InfoHash, PeerEndpoint, PeerEndpoint),
    ) -> Self {
        Self {
            info_hash,
            conn_pair: (self_endpoint, peer_endpoint),
        }
    }
}

impl ConnId {
    // For convenience.
    pub fn info_hash(&self) -> InfoHash {
        self.info_hash.clone()
    }

    pub fn self_endpoint(&self) -> PeerEndpoint {
        self.conn_pair.0
    }

    pub fn peer_endpoint(&self) -> PeerEndpoint {
        self.conn_pair.1
    }
}
