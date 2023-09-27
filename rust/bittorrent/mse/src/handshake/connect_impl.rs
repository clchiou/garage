//! Implementation of `ConnectSide` of `Handshake`

use std::io;

use bytes::{Buf, BufMut};
use snafu::prelude::*;
use tokio::time;

use g1_tokio::bstream::{transform::Transform, StreamBuffer, StreamRecv, StreamSend};

use crate::{
    error::{Error, ExpectCryptoSelectSnafu, IoSnafu},
    MseStream,
};

use super::{
    encode_size, load_crypto_provide, timeout, ConnectSide, Handshake, CRYPTO_PLAINTEXT,
    CRYPTO_RC4, PADDING_SIZE_RANGE, VC,
};

// Send empty initial payload for now.
const SELF_INITIAL_PAYLOAD: [u8; 0] = [];

impl<'a, Stream> Handshake<'a, Stream, ConnectSide>
where
    Stream: StreamRecv<Error = io::Error> + StreamSend<Error = io::Error> + Send,
{
    pub(super) async fn handshake(self) -> Result<MseStream<Stream>, Error> {
        time::timeout(*timeout(), self.handshake_impl())
            .await
            .map_err(|_| Error::Timeout)?
    }

    async fn handshake_impl(mut self) -> Result<MseStream<Stream>, Error> {
        self.exchange_key().await?;

        let hash_1 = self.compute_hash_1();
        let hash_2 = self.compute_hash_2();
        {
            let mut buffer = self.stream.send_buffer();
            buffer.put_slice(&hash_1);
            buffer.put_slice(&hash_2);
        }
        let crypto_provide = load_crypto_provide();
        self.put_crypto_provide(crypto_provide);
        self.stream.send_all().await.context(IoSnafu)?;

        // Receive padding_b and VC.
        let mut vc = VC;
        self.decrypt.as_mut().unwrap().transform(&mut vc);
        self.resynchronize(&vc, *PADDING_SIZE_RANGE.end() + vc.len())
            .await?;

        let crypto_select = self.recv_decrypt_u32().await?;
        let unknown = crypto_select & !(CRYPTO_PLAINTEXT | CRYPTO_RC4);
        if unknown != 0 {
            tracing::warn!(unknown, "unknown crypto_select bits");
        }
        ensure!(
            (crypto_select & crypto_provide) != 0,
            ExpectCryptoSelectSnafu {
                crypto_select,
                expect: crypto_provide,
            },
        );

        self.recv_padding().await?;

        Ok(self.finish(crypto_select))
    }

    fn put_crypto_provide(&mut self, crypto_provide: u32) {
        let mut buffer = self.stream.send_buffer();
        let start = buffer.remaining();
        buffer.put_slice(&VC);
        buffer.put_slice(&crypto_provide.to_be_bytes());
        buffer.put_slice(&encode_size(0)); // Send empty padding_c for now.
        buffer.put_slice(&encode_size(SELF_INITIAL_PAYLOAD.len()));
        buffer.put_slice(&SELF_INITIAL_PAYLOAD);
        let end = buffer.remaining();
        self.encrypt
            .as_mut()
            .unwrap()
            .transform(&mut buffer[start..end]);
    }
}
