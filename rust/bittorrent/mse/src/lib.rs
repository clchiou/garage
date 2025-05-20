//! Message Stream Encryption (MSE)

pub mod error;

mod cipher;
mod handshake;

use std::io::Error;

use sha1::{Digest, Sha1, Sha1Core, digest::Output};

use g1_tokio::{
    bstream::{StreamRecv, StreamSend, transform::DuplexTransformer},
    io::DynStream,
};

use self::cipher::{MseRc4, Plaintext};

pub use self::handshake::{accept, connect};

g1_param::define!(rc4_enable: bool = true);

// Implementer's Notes: Our strategy is to defer the creation of trait objects to the latest
// possible point, as Rust is not great in supporting trait objects.
#[derive(Debug)]
pub enum MseStream<Stream> {
    // `MseRc4` is wrapped inside a `Box` due to its size.
    Rc4(DuplexTransformer<Stream, Box<MseRc4>, Box<MseRc4>>),
    Plaintext(DuplexTransformer<Stream, Plaintext, Plaintext>),
}

impl<Stream> MseStream<Stream> {
    pub(crate) fn new_rc4(stream: Stream, recv: Box<MseRc4>, send: Box<MseRc4>) -> Self {
        Self::Rc4(DuplexTransformer::new(stream, recv, send))
    }

    pub fn new_plaintext(stream: Stream) -> Self {
        Self::Plaintext(DuplexTransformer::new(stream, Plaintext, Plaintext))
    }
}

impl<'a, Stream> From<MseStream<Stream>> for DynStream<'a>
where
    Stream: StreamRecv<Error = Error> + StreamSend<Error = Error> + Send + 'a,
{
    fn from(stream: MseStream<Stream>) -> Self {
        match stream {
            MseStream::Rc4(stream) => Box::new(stream),
            MseStream::Plaintext(stream) => Box::new(stream),
        }
    }
}

pub(crate) const HASH_SIZE: usize = 20;

pub(crate) fn compute_hash<'a, I>(data_iter: I) -> Output<Sha1Core>
where
    I: IntoIterator<Item = &'a [u8]>,
{
    let mut hasher = Sha1::new();
    for data in data_iter {
        hasher.update(data);
    }
    hasher.finalize()
}
