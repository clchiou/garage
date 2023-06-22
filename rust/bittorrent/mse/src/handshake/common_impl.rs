//! Implementation of Common Parts of `Handshake`

use std::io;
use std::marker::PhantomData;

use bytes::{Buf, BufMut, BytesMut};
use crypto_bigint::ArrayEncoding;
use rand::Rng;
use snafu::prelude::*;
use tokio::time;

use g1_base::ops::SliceCompoundAssignOp;
use g1_base::slice::SliceExt;
use g1_tokio::bstream::{transform::Transform, StreamBuffer, StreamRecv, StreamSend};

use bittorrent_base::PROTOCOL_ID;

use crate::{
    cipher::Plaintext,
    compute_hash,
    error::{
        Error, ExpectPaddingSizeSnafu, ExpectRecvPublicKeySizeSnafu, ExpectRecvSnafu,
        ExpectResynchronizeSnafu, IoSnafu,
    },
    MseStream, HASH_SIZE,
};

use super::{
    dh, recv_public_key_timeout, DhKey, Handshake, HandshakeSide, CRYPTO_PLAINTEXT, CRYPTO_RC4,
    DH_KEY_NUM_BYTES, PADDING_SIZE_RANGE,
};

const REQ1: &[u8] = b"req1";
const REQ2: &[u8] = b"req2";
const REQ3: &[u8] = b"req3";

impl<'a, Stream, Side> Handshake<'a, Stream, Side> {
    pub(super) fn new(stream: Stream, info_hash: &'a [u8]) -> Self {
        let private_key = dh::generate_private_key();
        let self_public_key = dh::compute_public_key(&private_key);
        Self {
            stream,
            info_hash,
            private_key,
            self_public_key,
            secret: Default::default(),
            decrypt: None,
            encrypt: None,
            _side: PhantomData,
        }
    }

    pub(super) fn compute_hash_1(&self) -> [u8; HASH_SIZE] {
        compute_hash([REQ1, &self.secret]).into()
    }

    pub(super) fn compute_hash_2(&self) -> [u8; HASH_SIZE] {
        let mut hash_2 = compute_hash([REQ2, self.info_hash]);
        {
            let mut hash_2 = SliceCompoundAssignOp(&mut hash_2);
            hash_2 ^= compute_hash([REQ3, &self.secret]);
        }
        hash_2.into()
    }

    pub(super) fn finish(mut self, crypto_select: u32) -> MseStream<Stream> {
        // Prefer CRYPTO_RC4 over CRYPTO_PLAINTEXT.
        if (crypto_select & CRYPTO_RC4) != 0 {
            tracing::debug!("handshake finish: rc4");
            MseStream::new(
                self.stream,
                self.decrypt.take().unwrap(),
                self.encrypt.take().unwrap(),
            )
        } else {
            assert_ne!(crypto_select & CRYPTO_PLAINTEXT, 0);
            tracing::debug!("handshake finish: plaintext");
            MseStream::new(self.stream, Box::new(Plaintext), Box::new(Plaintext))
        }
    }
}

impl<'a, Stream, Side> Handshake<'a, Stream, Side>
where
    Stream: StreamRecv<Error = io::Error> + StreamSend<Error = io::Error> + Send,
    Side: HandshakeSide,
{
    /// Exchanges the public key and returns false if the peer does not support MSE.
    pub(super) async fn exchange_key(&mut self) -> Result<bool, Error> {
        self.put_self_public_key();
        self.stream.send_all().await.context(IoSnafu)?;
        if self.check_peer_not_implement_mse().await? {
            return Ok(false);
        }
        self.recv_peer_public_key().await?;
        Ok(true)
    }

    fn put_self_public_key(&mut self) {
        let mut buffer = self.stream.send_buffer();
        buffer.put_slice(&self.self_public_key.to_be_byte_array());
        put_random_padding(&mut buffer);
    }

    async fn check_peer_not_implement_mse(&mut self) -> Result<bool, Error> {
        self.stream
            .recv_fill(1 + PROTOCOL_ID.len())
            .await
            .context(IoSnafu)?;
        let buffer = self.stream.recv_buffer();
        Ok(usize::from(buffer[0]) == PROTOCOL_ID.len()
            && &buffer[1..1 + PROTOCOL_ID.len()] == PROTOCOL_ID)
    }

    async fn recv_peer_public_key(&mut self) -> Result<(), Error> {
        time::timeout(
            *recv_public_key_timeout(),
            self.stream.recv_fill(DH_KEY_NUM_BYTES),
        )
        .await
        .map_err(|_| Error::RecvPublicKeyTimeout)?
        .context(IoSnafu)?;
        let peer_public_key;
        {
            let mut buffer = self.stream.recv_buffer();
            ensure!(
                buffer.len() <= DH_KEY_NUM_BYTES + PADDING_SIZE_RANGE.end(),
                ExpectRecvPublicKeySizeSnafu { size: buffer.len() },
            );
            peer_public_key = DhKey::from_be_slice(&buffer[0..DH_KEY_NUM_BYTES]);
            buffer.advance(DH_KEY_NUM_BYTES);
        }
        self.set_peer_public_key(peer_public_key);
        Ok(())
    }

    fn set_peer_public_key(&mut self, peer_public_key: DhKey) {
        let secret = dh::compute_secret(&peer_public_key, &self.private_key);
        let (decrypt, encrypt) = Side::new_mse_rc4(&secret, self.info_hash);
        self.decrypt = Some(Box::new(decrypt));
        self.encrypt = Some(Box::new(encrypt));
        self.secret = secret.to_be_byte_array();
    }
}

impl<'a, Stream, Side> Handshake<'a, Stream, Side>
where
    Stream: StreamRecv<Error = io::Error> + Send,
{
    /// Finds the `pattern` in the first `upper_bound` bytes of data.
    pub(super) async fn resynchronize(
        &mut self,
        pattern: &[u8],
        upper_bound: usize,
    ) -> Result<(), Error> {
        let mut size = 0;
        loop {
            self.stream
                .recv_fill(pattern.len())
                .await
                .context(IoSnafu)?;
            let mut buffer = self.stream.buffer();
            match buffer.as_ref().find(pattern) {
                Some(i) => {
                    let j = i + pattern.len(); // buffer[i..j] == pattern
                    size += j;
                    ensure!(
                        size <= upper_bound,
                        ExpectResynchronizeSnafu {
                            size,
                            expect: upper_bound,
                        },
                    );
                    buffer.advance(j);
                    return Ok(());
                }
                None => {
                    let end = size + buffer.remaining();
                    ensure!(
                        end <= upper_bound,
                        ExpectResynchronizeSnafu {
                            size: end,
                            expect: upper_bound,
                        },
                    );
                    let j = buffer.remaining() - pattern.len() + 1;
                    size += j;
                    buffer.advance(j);
                }
            }
        }
    }

    pub(super) async fn recv_expect(
        &mut self,
        name: &'static str,
        expect: &[u8],
    ) -> Result<(), Error> {
        self.stream.recv_fill(expect.len()).await.context(IoSnafu)?;
        let mut buffer = self.stream.buffer();
        let actual = &buffer[0..expect.len()];
        ensure!(
            actual == expect,
            ExpectRecvSnafu {
                name,
                actual: actual.to_vec(),
                expect: expect.to_vec(),
            },
        );
        buffer.advance(expect.len());
        Ok(())
    }

    pub(super) async fn recv_decrypt_u32(&mut self) -> Result<u32, Error> {
        self.stream.recv_fill(4).await.context(IoSnafu)?;
        let mut buffer = self.stream.buffer();
        self.decrypt.as_mut().unwrap().transform(&mut buffer[0..4]);
        Ok(buffer.get_u32())
    }

    pub(super) async fn recv_decrypt_size(&mut self) -> Result<usize, Error> {
        self.stream.recv_fill(2).await.context(IoSnafu)?;
        let mut buffer = self.stream.buffer();
        self.decrypt.as_mut().unwrap().transform(&mut buffer[0..2]);
        Ok(buffer.get_u16().try_into().unwrap())
    }

    pub(super) async fn recv_padding(&mut self) -> Result<(), Error> {
        let size = self.recv_decrypt_size().await?;
        ensure!(
            PADDING_SIZE_RANGE.contains(&size),
            ExpectPaddingSizeSnafu { size },
        );
        self.stream.recv_fill(size).await.context(IoSnafu)?;
        let mut buffer = self.stream.buffer();
        self.decrypt
            .as_mut()
            .unwrap()
            .transform(&mut buffer[0..size]);
        buffer.advance(size);
        Ok(())
    }
}

fn put_random_padding(buffer: &mut BytesMut) {
    let mut padding = [0u8; *PADDING_SIZE_RANGE.end()];
    let mut rng = rand::thread_rng();
    let size = rng.gen_range(PADDING_SIZE_RANGE);
    rng.fill(&mut padding[0..size]);
    buffer.put_slice(&padding[0..size]);
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use tokio::io::AsyncWriteExt;

    use g1_tokio::io::RecvStream;

    use super::*;

    #[tokio::test]
    async fn resynchronize() {
        async fn test_ok(data: &[u8], pattern: &[u8], upper_bound: usize, expect: &[u8]) {
            let (stream, mut mock) = RecvStream::new_mock(4096);
            let mut handshake = Handshake::<_, ()>::new(stream, b"");
            mock.write_all(data).await.unwrap();
            assert_matches!(handshake.resynchronize(pattern, upper_bound).await, Ok(()));
            assert_eq!(handshake.stream.buffer().as_ref(), expect);
        }

        async fn test_err(data: &[u8], pattern: &[u8], upper_bound: usize, expect_size: usize) {
            let (stream, mut mock) = RecvStream::new_mock(4096);
            let mut handshake = Handshake::<_, ()>::new(stream, b"");
            mock.write_all(data).await.unwrap();
            assert_matches!(
                handshake.resynchronize(pattern, upper_bound).await,
                Err(Error::ExpectResynchronize {
                    size,
                    expect,
                })
                if size == expect_size && expect == upper_bound
            );
        }

        test_ok(b"xabcdef", b"x", 4, b"abcdef").await;
        test_ok(b"axbcdef", b"x", 4, b"bcdef").await;
        test_ok(b"abxcdef", b"x", 4, b"cdef").await;
        test_ok(b"abcxdef", b"x", 4, b"def").await;
        test_err(b"abcdxef", b"x", 4, 5).await;
        test_err(b"abcdef", b"x", 4, 6).await;

        test_ok(b"xyabcdef", b"xy", 5, b"abcdef").await;
        test_ok(b"axybcdef", b"xy", 5, b"bcdef").await;
        test_ok(b"abxycdef", b"xy", 5, b"cdef").await;
        test_ok(b"abcxydef", b"xy", 5, b"def").await;
        test_err(b"abcdxyef", b"xy", 5, 6).await;
        test_err(b"abcdexyf", b"xy", 5, 7).await;
        test_err(b"abcdef", b"xy", 5, 6).await;
    }
}
