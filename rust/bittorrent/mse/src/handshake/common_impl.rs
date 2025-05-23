//! Implementation of Common Parts of `Handshake`

use std::io::Error;
use std::marker::PhantomData;

use bytes::{Buf, BufMut, BytesMut};
use crypto_bigint::ArrayEncoding;
use rand::Rng;
use snafu::prelude::*;
use tokio::time;

use g1_base::ops::SliceCompoundAssignOp;
use g1_base::slice::SliceExt;
use g1_tokio::bstream::{StreamBuffer, StreamRecv, StreamSend, transform::Transform};

use crate::{
    HASH_SIZE, MseStream, compute_hash,
    error::{
        self, ExpectPaddingSizeSnafu, ExpectRecvPublicKeySizeSnafu, ExpectRecvSnafu,
        ExpectResynchronizeSnafu,
    },
};

use super::{
    CRYPTO_PLAINTEXT, CRYPTO_RC4, DH_KEY_NUM_BYTES, DhKey, Handshake, HandshakeSide,
    PADDING_SIZE_RANGE, dh, recv_public_key_timeout,
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
}

impl<Stream, Side> Handshake<'_, Stream, Side>
where
    Stream: StreamRecv<Error = Error> + StreamSend<Error = Error> + Send,
    Side: HandshakeSide,
{
    pub(super) async fn exchange_key(&mut self) -> Result<(), Error> {
        self.put_self_public_key();
        self.stream.send_all().await?;
        self.recv_peer_public_key().await
    }

    fn put_self_public_key(&mut self) {
        let mut buffer = self.stream.send_buffer();
        buffer.put_slice(&self.self_public_key.to_be_byte_array());
        put_random_padding(&mut buffer);
    }

    async fn recv_peer_public_key(&mut self) -> Result<(), Error> {
        time::timeout(
            *recv_public_key_timeout(),
            self.stream.recv_fill(DH_KEY_NUM_BYTES),
        )
        .await
        .map_err(|_| error::Error::RecvPublicKeyTimeout)??;
        let peer_public_key;
        {
            let buffer = self.stream.recv_buffer();
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

    pub(super) fn finish(mut self, crypto_select: u32) -> MseStream<Stream> {
        assert!(self.stream.send_buffer().is_empty());

        // Prefer CRYPTO_RC4 over CRYPTO_PLAINTEXT.
        if (crypto_select & CRYPTO_RC4) != 0 {
            tracing::debug!("handshake finish: rc4");

            // In case we have already received some data from the peer.
            self.decrypt
                .as_mut()
                .unwrap()
                .transform(self.stream.recv_buffer());

            MseStream::new_rc4(
                self.stream,
                self.decrypt.take().unwrap(),
                self.encrypt.take().unwrap(),
            )
        } else {
            assert_ne!(crypto_select & CRYPTO_PLAINTEXT, 0);
            tracing::debug!("handshake finish: plaintext");
            MseStream::new_plaintext(self.stream)
        }
    }
}

impl<Stream, Side> Handshake<'_, Stream, Side>
where
    Stream: StreamRecv<Error = Error> + Send,
{
    /// Finds the `pattern` in the first `upper_bound` bytes of data.
    pub(super) async fn resynchronize(
        &mut self,
        pattern: &[u8],
        upper_bound: usize,
    ) -> Result<(), Error> {
        let mut size = 0;
        loop {
            self.stream.recv_fill(pattern.len()).await?;
            let buffer = self.stream.buffer();
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
        self.stream.recv_fill(expect.len()).await?;
        let buffer = self.stream.buffer();
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
        self.stream.recv_fill(4).await?;
        let buffer = self.stream.buffer();
        self.decrypt.as_mut().unwrap().transform(&mut buffer[0..4]);
        Ok(buffer.get_u32())
    }

    pub(super) async fn recv_decrypt_size(&mut self) -> Result<usize, Error> {
        self.stream.recv_fill(2).await?;
        let buffer = self.stream.buffer();
        self.decrypt.as_mut().unwrap().transform(&mut buffer[0..2]);
        Ok(buffer.get_u16().into())
    }

    pub(super) async fn recv_padding(&mut self) -> Result<(), Error> {
        let size = self.recv_decrypt_size().await?;
        ensure!(
            PADDING_SIZE_RANGE.contains(&size),
            ExpectPaddingSizeSnafu { size },
        );
        self.stream.recv_fill(size).await?;
        let buffer = self.stream.buffer();
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
    let mut rng = rand::rng();
    let size = rng.random_range(PADDING_SIZE_RANGE);
    rng.fill(&mut padding[0..size]);
    buffer.put_slice(&padding[0..size]);
}

#[cfg(test)]
mod tests {
    use tokio::io::AsyncWriteExt;

    use g1_tokio::io::RecvStream;

    use super::*;

    #[tokio::test]
    async fn resynchronize() {
        async fn test_ok(data: &[u8], pattern: &[u8], upper_bound: usize, expect: &[u8]) {
            let (stream, mut mock) = RecvStream::new_mock(4096);
            let mut handshake = Handshake::<_, ()>::new(stream, b"");
            mock.write_all(data).await.unwrap();
            handshake.resynchronize(pattern, upper_bound).await.unwrap();
            assert_eq!(handshake.stream.buffer().as_ref(), expect);
        }

        async fn test_err(data: &[u8], pattern: &[u8], upper_bound: usize, expect_size: usize) {
            let (stream, mut mock) = RecvStream::new_mock(4096);
            let mut handshake = Handshake::<_, ()>::new(stream, b"");
            mock.write_all(data).await.unwrap();
            assert_eq!(
                handshake
                    .resynchronize(pattern, upper_bound)
                    .await
                    .unwrap_err()
                    .downcast::<error::Error>()
                    .unwrap(),
                error::Error::ExpectResynchronize {
                    size: expect_size,
                    expect: upper_bound,
                },
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
