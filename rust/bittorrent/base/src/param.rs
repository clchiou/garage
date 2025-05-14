use std::sync::Arc;

use rand::prelude::*;
use serde::{de, Deserialize, Deserializer};

use crate::{PeerId, PEER_ID_SIZE};

impl PeerId {
    pub(crate) fn deserialize<'de, D>(deserializer: D) -> Result<Arc<[u8; PEER_ID_SIZE]>, D::Error>
    where
        D: Deserializer<'de>,
    {
        let hex = String::deserialize(deserializer)?;
        Ok(Arc::new(hex.as_bytes().try_into().map_err(|_| {
            de::Error::custom(format!("invalid peer id: {hex:?}"))
        })?))
    }

    pub(crate) fn generate() -> Self {
        Self::new(Self::random())
    }

    // TODO: Comply with BEP 20.
    fn random() -> [u8; PEER_ID_SIZE] {
        const CHARSET: &[u8] = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.-";
        let mut peer_id = [0u8; PEER_ID_SIZE];
        let mut rng = thread_rng();
        peer_id.fill_with(|| *CHARSET.choose(&mut rng).unwrap());
        peer_id
    }
}
