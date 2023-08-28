use std::array::TryFromSliceError;
use std::borrow::Borrow;
use std::sync::Arc;

use g1_base::fmt::{DebugExt, Hex};

pub const PROTOCOL_ID: &[u8] = b"BitTorrent protocol";

pub const INFO_HASH_SIZE: usize = 20;
pub const PIECE_HASH_SIZE: usize = 20;

#[cfg(feature = "param")]
g1_param::define!(pub recv_buffer_capacity: usize = 65536);
#[cfg(feature = "param")]
g1_param::define!(pub send_buffer_capacity: usize = 65536);

#[cfg(feature = "param")]
g1_param::define!(pub payload_size_limit: usize = 65536);

#[derive(Clone, DebugExt, Eq, Hash, PartialEq)]
pub struct InfoHash(#[debug(with = Hex)] Arc<[u8; INFO_HASH_SIZE]>);

impl<'a> TryFrom<&'a [u8]> for InfoHash {
    type Error = TryFromSliceError;

    fn try_from(info_hash: &'a [u8]) -> Result<InfoHash, TryFromSliceError> {
        info_hash.try_into().map(InfoHash::new)
    }
}

impl InfoHash {
    pub fn new(info_hash: [u8; INFO_HASH_SIZE]) -> Self {
        Self(Arc::new(info_hash))
    }
}

impl AsRef<[u8]> for InfoHash {
    fn as_ref(&self) -> &[u8] {
        self.0.as_ref()
    }
}

impl Borrow<[u8]> for InfoHash {
    fn borrow(&self) -> &[u8] {
        self.0.as_slice()
    }
}
