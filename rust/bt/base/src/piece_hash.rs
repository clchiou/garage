use std::borrow::Borrow;
use std::fmt;
use std::sync::Arc;

use serde::de::{Deserialize, Deserializer, Error as _};
use serde::ser::{Serialize, Serializer};
use snafu::prelude::*;

use g1_base::fmt::{DebugExt, Hex};

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub struct PieceHashes(#[debug(with = Hex)] Arc<[u8]>);

impl fmt::Display for PieceHashes {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        std::write!(f, "{:?}", Hex(&self.0))
    }
}

#[derive(Clone, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct PieceHash<'a>(&'a [u8; PIECE_HASH_SIZE]);

pub const PIECE_HASH_SIZE: usize = 20;

impl fmt::Debug for PieceHash<'_> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_tuple("PieceHash").field(&Hex(self.0)).finish()
    }
}

impl fmt::Display for PieceHash<'_> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        std::write!(f, "{:?}", Hex(self.0))
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("expect piece hashes size % {PIECE_HASH_SIZE} == 0: {size}"))]
pub struct PieceHashesError {
    size: usize,
}

impl<'de> Deserialize<'de> for PieceHashes {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        Self::new(serde_bytes::deserialize::<Vec<u8>, _>(deserializer)?.into())
            .map_err(D::Error::custom)
    }
}

impl Serialize for PieceHashes {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_bytes(&self.0)
    }
}

impl PieceHashes {
    pub fn new(piece_hashes: Arc<[u8]>) -> Result<Self, PieceHashesError> {
        let size = piece_hashes.len();
        ensure!(size % PIECE_HASH_SIZE == 0, PieceHashesSnafu { size });
        Ok(Self(piece_hashes))
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn len(&self) -> usize {
        self.0.len() / PIECE_HASH_SIZE
    }

    pub fn iter(&self) -> impl Iterator<Item = PieceHash<'_>> {
        unsafe { self.0.as_chunks_unchecked() }
            .iter()
            .map(PieceHash)
    }

    pub fn get(&self, index: usize) -> Option<PieceHash<'_>> {
        let index = index * PIECE_HASH_SIZE;
        self.0
            .get(index..index + PIECE_HASH_SIZE)
            .map(|slice| PieceHash(slice.try_into().expect("piece hash")))
    }
}

impl AsRef<[u8; PIECE_HASH_SIZE]> for PieceHash<'_> {
    fn as_ref(&self) -> &[u8; PIECE_HASH_SIZE] {
        self.0
    }
}

impl AsRef<[u8]> for PieceHash<'_> {
    fn as_ref(&self) -> &[u8] {
        self.0
    }
}

impl Borrow<[u8; PIECE_HASH_SIZE]> for PieceHash<'_> {
    fn borrow(&self) -> &[u8; PIECE_HASH_SIZE] {
        self.0
    }
}

impl Borrow<[u8]> for PieceHash<'_> {
    fn borrow(&self) -> &[u8] {
        self.0
    }
}
