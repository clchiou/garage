//! Message Stream Encryption (MSE)

#![feature(io_error_other)]
#![cfg_attr(test, feature(assert_matches))]

mod cipher;
mod error;
mod handshake;

use sha1::{digest::Output, Digest, Sha1, Sha1Core};

use g1_tokio::bstream::transform::{DuplexTransformer, Transform};

use self::cipher::Plaintext;

pub use self::error::Error;
pub use self::handshake::{accept, connect};

g1_param::define!(rc4_enable: bool = true);

type MseStream<Stream> = DuplexTransformer<Stream, DynTransform, DynTransform>;
type DynTransform = Box<dyn Transform + Send>;

pub fn wrap<Stream>(stream: Stream) -> MseStream<Stream> {
    MseStream::new(stream, Box::new(Plaintext), Box::new(Plaintext))
}

const HASH_SIZE: usize = 20;

fn compute_hash<'a, I>(data_iter: I) -> Output<Sha1Core>
where
    I: IntoIterator<Item = &'a [u8]>,
{
    let mut hasher = Sha1::new();
    for data in data_iter {
        hasher.update(data);
    }
    hasher.finalize()
}
