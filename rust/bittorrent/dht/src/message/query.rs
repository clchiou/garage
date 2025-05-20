use std::collections::BTreeMap;

use bitvec::prelude::*;

use g1_base::fmt::{DebugExt, Hex};

use bittorrent_bencode::{FormatDictionary, borrow};

use crate::NodeIdBitSlice;

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) enum Query<'a> {
    Ping(Ping<'a>),
    FindNode(FindNode<'a>),
    GetPeers(GetPeers<'a>),
    AnnouncePeer(AnnouncePeer<'a>),
}

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub(crate) struct Ping<'a> {
    #[debug(with = Hex)]
    pub(crate) id: &'a [u8],

    #[debug(with = FormatDictionary)]
    pub(crate) extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub(crate) struct FindNode<'a> {
    #[debug(with = Hex)]
    pub(crate) id: &'a [u8],
    #[debug(with = Hex)]
    pub(crate) target: &'a [u8],

    #[debug(with = FormatDictionary)]
    pub(crate) extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub(crate) struct GetPeers<'a> {
    #[debug(with = Hex)]
    pub(crate) id: &'a [u8],
    #[debug(with = Hex)]
    pub(crate) info_hash: &'a [u8],

    #[debug(with = FormatDictionary)]
    pub(crate) extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub(crate) struct AnnouncePeer<'a> {
    #[debug(with = Hex)]
    pub(crate) id: &'a [u8],
    #[debug(with = Hex)]
    pub(crate) info_hash: &'a [u8],
    pub(crate) port: u16,
    // TODO: BEP 5 specifies that `implied_port` is optional.  Should we use `bool` instead of
    // `Option<bool>` because "present false" is semantically equivalent to "not present"?
    pub(crate) implied_port: Option<bool>,
    #[debug(with = Hex)]
    pub(crate) token: &'a [u8],

    #[debug(with = FormatDictionary)]
    pub(crate) extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

impl<'a> Query<'a> {
    pub(crate) fn id(&self) -> &[u8] {
        match self {
            Self::Ping(ping) => ping.id,
            Self::FindNode(find_node) => find_node.id,
            Self::GetPeers(get_peers) => get_peers.id,
            Self::AnnouncePeer(announce_peer) => announce_peer.id,
        }
    }

    pub(crate) fn extra(&self) -> &BTreeMap<&'a [u8], borrow::Value<'a>> {
        match self {
            Self::Ping(ping) => &ping.extra,
            Self::FindNode(find_node) => &find_node.extra,
            Self::GetPeers(get_peers) => &get_peers.extra,
            Self::AnnouncePeer(announce_peer) => &announce_peer.extra,
        }
    }
}

impl<'a> Ping<'a> {
    pub(crate) fn new(id: &'a [u8]) -> Self {
        Self {
            id,
            extra: BTreeMap::new(),
        }
    }
}

impl<'a> FindNode<'a> {
    pub(crate) fn new(id: &'a [u8], target: &'a [u8]) -> Self {
        Self {
            id,
            target,
            extra: BTreeMap::new(),
        }
    }

    pub(crate) fn target_bits(&self) -> &NodeIdBitSlice {
        self.target.view_bits()
    }
}

impl<'a> GetPeers<'a> {
    pub(crate) fn new(id: &'a [u8], info_hash: &'a [u8]) -> Self {
        Self {
            id,
            info_hash,
            extra: BTreeMap::new(),
        }
    }

    pub(crate) fn info_hash_bits(&self) -> &NodeIdBitSlice {
        self.info_hash.view_bits()
    }
}

impl<'a> AnnouncePeer<'a> {
    pub(crate) fn new(
        id: &'a [u8],
        info_hash: &'a [u8],
        port: u16,
        implied_port: Option<bool>,
        token: &'a [u8],
    ) -> Self {
        Self {
            id,
            info_hash,
            port,
            implied_port,
            token,
            extra: BTreeMap::new(),
        }
    }
}
