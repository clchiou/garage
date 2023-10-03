use cipher::StreamCipher;
use crypto_bigint::ArrayEncoding;
use rc4::{consts::U20, Key, KeyInit, Rc4};

use g1_base::fmt::{DebugExt, InsertPlaceholder};
use g1_tokio::bstream::transform::Transform;

use super::{compute_hash, handshake::DhKey};

#[derive(Debug)]
pub struct Plaintext;

#[derive(DebugExt)]
pub struct MseRc4(#[debug(with = InsertPlaceholder)] Rc4<Rc4KeySize>);

type Rc4KeySize = U20;
type Rc4Key = Key<Rc4KeySize>;

const RC4_KEY_A: &[u8] = b"keyA"; // Key for the A-to-B traffic.
const RC4_KEY_B: &[u8] = b"keyB"; // Key for the B-to-A traffic.
const RC4_DISCARD_NUM_BYTES: usize = 1024;

impl Transform for Plaintext {
    fn transform(&mut self, _: &mut [u8]) {
        // Nothing to do here.
    }
}

impl MseRc4 {
    /// Creates a `(decrypt, encrypt)` pair for the connect side.
    pub(super) fn connect_new(secret: &DhKey, skey: &[u8]) -> (Self, Self) {
        let (key_a, key_b) = Self::new_key_pair(secret, skey);
        (Self::new(&key_b), Self::new(&key_a))
    }

    /// Creates a `(decrypt, encrypt)` pair for the accept side.
    pub(super) fn accept_new(secret: &DhKey, skey: &[u8]) -> (Self, Self) {
        let (key_a, key_b) = Self::new_key_pair(secret, skey);
        (Self::new(&key_a), Self::new(&key_b))
    }

    fn new_key_pair(secret: &DhKey, skey: &[u8]) -> (Rc4Key, Rc4Key) {
        let secret = secret.to_be_byte_array();
        (
            compute_hash([RC4_KEY_A, &secret, skey]),
            compute_hash([RC4_KEY_B, &secret, skey]),
        )
    }

    fn new(key: &Rc4Key) -> Self {
        let mut rc4 = Rc4::new(key);
        let mut discard = [0u8; RC4_DISCARD_NUM_BYTES];
        rc4.apply_keystream(&mut discard);
        Self(rc4)
    }
}

impl Transform for MseRc4 {
    fn transform(&mut self, buffer: &mut [u8]) {
        self.0.apply_keystream(buffer);
    }
}

impl Transform for Box<MseRc4> {
    fn transform(&mut self, buffer: &mut [u8]) {
        (**self).transform(buffer)
    }
}
