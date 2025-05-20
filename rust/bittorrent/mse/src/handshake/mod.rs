mod accept_impl;
mod common_impl;
mod connect_impl;
mod dh;

use std::io::Error;
use std::marker::PhantomData;
use std::ops::RangeInclusive;
use std::time::Duration;

use crypto_bigint::{ByteArray, U768};

use g1_tokio::bstream::{StreamRecv, StreamSend};

use crate::{MseStream, cipher::MseRc4};

g1_param::define!(
    timeout: Duration = Duration::from_secs(60);
    parse = g1_param::parse::duration;
);
g1_param::define!(
    recv_public_key_timeout: Duration = Duration::from_secs(30);
    parse = g1_param::parse::duration;
);

pub async fn connect<Stream>(stream: Stream, info_hash: &[u8]) -> Result<MseStream<Stream>, Error>
where
    Stream: StreamRecv<Error = Error> + StreamSend<Error = Error> + Send,
{
    Handshake::<_, ConnectSide>::new(stream, info_hash)
        .handshake()
        .await
}

pub async fn accept<Stream>(stream: Stream, info_hash: &[u8]) -> Result<MseStream<Stream>, Error>
where
    Stream: StreamRecv<Error = Error> + StreamSend<Error = Error> + Send,
{
    Handshake::<_, AcceptSide>::new(stream, info_hash)
        .handshake()
        .await
}

// Exposed to `cipher`.
pub(crate) type DhKey = U768;

const DH_KEY_NUM_BITS: usize = 768;
const DH_KEY_NUM_BYTES: usize = DH_KEY_NUM_BITS / 8;

// Exposed to `error`.
pub(crate) const PADDING_SIZE_RANGE: RangeInclusive<usize> = 0..=512;

// Verification constant.
const VC: [u8; 8] = [0u8; 8];

const CRYPTO_PLAINTEXT: u32 = 0x00000001;
const CRYPTO_RC4: u32 = 0x00000002;

struct Handshake<'a, Stream, Side> {
    stream: Stream,
    info_hash: &'a [u8],
    private_key: DhKey,
    self_public_key: DhKey,
    secret: ByteArray<DhKey>,
    decrypt: Option<Box<MseRc4>>,
    encrypt: Option<Box<MseRc4>>,
    _side: PhantomData<Side>,
}

trait HandshakeSide {
    fn new_mse_rc4(secret: &DhKey, skey: &[u8]) -> (MseRc4, MseRc4);
}

struct ConnectSide;
struct AcceptSide;

impl HandshakeSide for ConnectSide {
    fn new_mse_rc4(secret: &DhKey, skey: &[u8]) -> (MseRc4, MseRc4) {
        MseRc4::connect_new(secret, skey)
    }
}

impl HandshakeSide for AcceptSide {
    fn new_mse_rc4(secret: &DhKey, skey: &[u8]) -> (MseRc4, MseRc4) {
        MseRc4::accept_new(secret, skey)
    }
}

fn load_crypto_provide() -> u32 {
    CRYPTO_PLAINTEXT | if *crate::rc4_enable() { CRYPTO_RC4 } else { 0 }
}

fn encode_size(x: usize) -> [u8; 2] {
    u16::try_from(x).unwrap().to_be_bytes()
}

#[cfg(test)]
mod tests {
    use bytes::BufMut;
    use tokio::io;

    use g1_tokio::{
        bstream::StreamBuffer,
        io::{DynStream, Stream},
    };

    use super::*;

    #[tokio::test]
    async fn handshake() {
        let (stream_a, mut mock_a) = Stream::new_mock(4096);
        let (stream_b, mut mock_b) = Stream::new_mock(4096);

        let peer_a_task = tokio::spawn(async move {
            let mut stream_a = DynStream::from(connect(stream_a, b"foo").await?);
            stream_a.send_buffer().put_slice(b"ping");
            stream_a.send_all().await?;
            stream_a.recv_fill(4).await?;
            assert_eq!(stream_a.recv_buffer().as_ref(), b"pong");
            Ok::<_, Error>(())
        });
        let peer_b_task = tokio::spawn(async move {
            let mut stream_b = DynStream::from(accept(stream_b, b"foo").await?);
            stream_b.recv_fill(4).await?;
            assert_eq!(stream_b.recv_buffer().as_ref(), b"ping");
            stream_b.send_buffer().put_slice(b"pong");
            stream_b.send_all().await?;
            Ok::<_, Error>(())
        });
        let copy_task =
            tokio::spawn(async move { io::copy_bidirectional(&mut mock_a, &mut mock_b).await });

        peer_a_task.await.unwrap().unwrap();
        peer_b_task.await.unwrap().unwrap();
        copy_task.await.unwrap().unwrap();
    }

    #[tokio::test]
    async fn peer_not_implement_mse() {
        let (mut stream_a, mut mock_a) = Stream::new_mock(4096);
        let (stream_b, mut mock_b) = Stream::new_mock(4096);

        let peer_a_task = tokio::spawn(async move {
            stream_a.send_buffer().put_slice(b"\x13BitTorrent protocol");
            stream_a.send_all().await?;
            stream_a.send_buffer().put_slice(b"ping");
            stream_a.send_all().await?;
            stream_a.recv_fill(4).await?;
            assert_eq!(stream_a.recv_buffer().as_ref(), b"pong");
            Ok::<_, Error>(())
        });
        let peer_b_task = tokio::spawn(async move {
            let mut stream_b = DynStream::from(accept(stream_b, b"foo").await?);
            stream_b.recv_fill(1 + 19 + 4).await?;
            assert_eq!(
                stream_b.recv_buffer().as_ref(),
                b"\x13BitTorrent protocolping",
            );
            stream_b.send_buffer().put_slice(b"pong");
            stream_b.send_all().await?;
            Ok::<_, Error>(())
        });
        let copy_task =
            tokio::spawn(async move { io::copy_bidirectional(&mut mock_a, &mut mock_b).await });

        peer_a_task.await.unwrap().unwrap();
        peer_b_task.await.unwrap().unwrap();
        copy_task.await.unwrap().unwrap();
    }
}
