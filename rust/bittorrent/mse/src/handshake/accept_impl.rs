//! Implementation of `AcceptSide` of `Handshake`

use std::io;

use bytes::{Buf, BufMut};
use snafu::prelude::*;
use tokio::time;

use g1_tokio::bstream::{transform::Transform, StreamBuffer, StreamRecv, StreamSend};

use bittorrent_base::{payload_size_limit, PROTOCOL_ID};

use crate::{
    error::{Error, ExpectCryptoProvideSnafu, ExpectPayloadSizeSnafu, IoSnafu},
    MseStream,
};

use super::{
    encode_size, load_crypto_provide, timeout, AcceptSide, Handshake, CRYPTO_PLAINTEXT, CRYPTO_RC4,
    PADDING_SIZE_RANGE, VC,
};

impl<'a, Stream> Handshake<'a, Stream, AcceptSide>
where
    Stream: StreamRecv<Error = io::Error> + StreamSend<Error = io::Error> + Send,
{
    pub(super) async fn handshake(self) -> Result<MseStream<Stream>, Error> {
        time::timeout(*timeout(), self.handshake_impl())
            .await
            .map_err(|_| Error::Timeout)?
    }

    async fn handshake_impl(mut self) -> Result<MseStream<Stream>, Error> {
        if self.check_peer_not_implement_mse().await? {
            return Ok(self.finish(CRYPTO_PLAINTEXT));
        }

        self.exchange_key().await?;

        // Receive padding_a and hashes.
        let hash_1 = self.compute_hash_1();
        self.resynchronize(&hash_1, *PADDING_SIZE_RANGE.end() + hash_1.len())
            .await?;
        self.recv_expect("hash_2", &self.compute_hash_2()).await?;

        let mut vc = VC;
        self.decrypt.as_mut().unwrap().transform(&mut vc);
        self.recv_expect("vc", &vc).await?;

        let peer_crypto_provide = self.recv_decrypt_u32().await?;
        let unknown = peer_crypto_provide & !(CRYPTO_PLAINTEXT | CRYPTO_RC4);
        if unknown != 0 {
            tracing::info!(unknown, "unknown crypto_provide bits");
        }
        let self_crypto_provide = load_crypto_provide();
        let crypto_provide = peer_crypto_provide & self_crypto_provide;
        ensure!(
            crypto_provide != 0,
            ExpectCryptoProvideSnafu {
                crypto_provide: peer_crypto_provide,
                expect: self_crypto_provide,
            }
        );

        // Prefer CRYPTO_RC4 over CRYPTO_PLAINTEXT.
        let crypto_select = if (crypto_provide & CRYPTO_RC4) != 0 {
            CRYPTO_RC4
        } else {
            assert_ne!(crypto_provide & CRYPTO_PLAINTEXT, 0);
            CRYPTO_PLAINTEXT
        };

        // Receive padding_c.
        self.recv_padding().await?;

        self.recv_initial_payload().await?;

        self.put_crypto_select(crypto_select);
        self.stream.send_all().await.context(IoSnafu)?;

        Ok(self.finish(crypto_select))
    }

    async fn check_peer_not_implement_mse(&mut self) -> Result<bool, Error> {
        self.stream
            .recv_fill(1 + PROTOCOL_ID.len())
            .await
            .context(IoSnafu)?;
        Ok({
            let buffer = self.stream.recv_buffer();
            usize::from(buffer[0]) == PROTOCOL_ID.len()
                && &buffer[1..1 + PROTOCOL_ID.len()] == PROTOCOL_ID
        })
    }

    async fn recv_initial_payload(&mut self) -> Result<(), Error> {
        let size = self.recv_decrypt_size().await?;
        let limit = *payload_size_limit();
        ensure!(
            size <= limit,
            ExpectPayloadSizeSnafu {
                size,
                expect: limit,
            },
        );
        self.stream.recv_fill(size).await.context(IoSnafu)?;
        let mut buffer = self.stream.recv_buffer();
        self.decrypt
            .as_mut()
            .unwrap()
            .transform(&mut buffer[0..size]);
        Ok(())
    }

    fn put_crypto_select(&mut self, crypto_select: u32) {
        let mut buffer = self.stream.send_buffer();
        let start = buffer.remaining();
        buffer.put_slice(&VC);
        buffer.put_slice(&crypto_select.to_be_bytes());
        buffer.put_slice(&encode_size(0)); // Send empty padding_d for now.
        let end = buffer.remaining();
        self.encrypt
            .as_mut()
            .unwrap()
            .transform(&mut buffer[start..end]);
    }
}
