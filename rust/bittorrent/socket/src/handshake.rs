use std::io::Error;

use bitvec::prelude::*;
use bytes::{Buf, BufMut};
use snafu::prelude::*;
use tokio::time;

use g1_base::fmt::Hex;
use g1_tokio::bstream::{StreamRecv, StreamSend};

use bittorrent_base::{Features, InfoHash, PeerId, INFO_HASH_SIZE, PEER_ID_SIZE, PROTOCOL_ID};

use crate::error;

type Reserved = [u8; RESERVED_SIZE];
type ReservedBits = BitSlice<u8, Msb0>;

const RESERVED_SIZE: usize = 8;

const RESERVED_AZUREUS_MESSAGING: usize = 0;
const RESERVED_LOCATION_AWARE: usize = 20;
const RESERVED_EXTENSION: usize = 43; // BEP 10
const RESERVED_EXTENSION_NEGOTIATION_0: usize = 46;
const RESERVED_EXTENSION_NEGOTIATION_1: usize = 47;
const RESERVED_HYBRID: usize = 59; // BEP 52
const RESERVED_NAT_TRAVERSAL: usize = 60;
const RESERVED_FAST: usize = 61; // BEP 6
const RESERVED_XBT_PEER_EXCHANGE: usize = 62;
const RESERVED_DHT: usize = 63; // BEP 5

const RESERVED_OFFSETS: &[usize] = &[
    RESERVED_AZUREUS_MESSAGING,
    RESERVED_LOCATION_AWARE,
    RESERVED_EXTENSION,
    RESERVED_EXTENSION_NEGOTIATION_0,
    RESERVED_EXTENSION_NEGOTIATION_1,
    RESERVED_HYBRID,
    RESERVED_NAT_TRAVERSAL,
    RESERVED_FAST,
    RESERVED_XBT_PEER_EXCHANGE,
    RESERVED_DHT,
];

pub(crate) async fn connect<Stream>(
    stream: &mut Stream,
    info_hash: InfoHash,
    self_id: PeerId,
    self_features: Features,
    expect_peer_id: Option<PeerId>,
) -> Result<(PeerId, Features), Error>
where
    Stream: StreamRecv<Error = Error> + StreamSend<Error = Error> + Send,
{
    time::timeout(*crate::handshake_timeout(), async {
        send_handshake(stream, info_hash.clone(), self_features).await?;
        let peer_features = recv_handshake(stream, info_hash).await?;
        send_self_id(stream, self_id).await?;
        let peer_id = recv_peer_id(stream, expect_peer_id).await?;
        Ok((peer_id, peer_features))
    })
    .await
    .map_err(|_| error::Error::HandshakeTimeout)?
}

pub(crate) async fn accept<Stream>(
    stream: &mut Stream,
    info_hash: InfoHash,
    self_id: PeerId,
    self_features: Features,
    expect_peer_id: Option<PeerId>,
) -> Result<(PeerId, Features), Error>
where
    Stream: StreamRecv<Error = Error> + StreamSend<Error = Error> + Send,
{
    time::timeout(*crate::handshake_timeout(), async {
        // TODO: BEP 3 suggests that if we are serving multiple torrents on a single port (which we
        // are not currently), we may wait for the incoming connection's info hash and then send
        // the corresponding one.
        let peer_features = recv_handshake(stream, info_hash.clone()).await?;
        send_handshake(stream, info_hash, self_features).await?;
        send_self_id(stream, self_id).await?;
        let peer_id = recv_peer_id(stream, expect_peer_id).await?;
        Ok((peer_id, peer_features))
    })
    .await
    .map_err(|_| error::Error::HandshakeTimeout)?
}

async fn recv_handshake<Stream>(stream: &mut Stream, info_hash: InfoHash) -> Result<Features, Error>
where
    Stream: StreamRecv<Error = Error> + Send,
{
    stream.recv_fill(1).await?;
    let size = usize::from(stream.buffer().get_u8());
    ensure!(
        size == PROTOCOL_ID.len(),
        error::ExpectProtocolIdSizeSnafu {
            size,
            expect: PROTOCOL_ID.len(),
        },
    );

    stream.recv_fill(PROTOCOL_ID.len()).await?;
    {
        let buffer = stream.buffer();
        ensure!(
            buffer.starts_with(PROTOCOL_ID),
            error::ExpectProtocolIdSnafu {
                protocol_id: buffer[0..PROTOCOL_ID.len()].escape_ascii().to_string(),
                expect: PROTOCOL_ID.escape_ascii().to_string(),
            },
        );
        buffer.advance(PROTOCOL_ID.len());
    }

    stream.recv_fill(RESERVED_SIZE).await?;
    let mut reserved = Reserved::default();
    stream.buffer().copy_to_slice(&mut reserved);
    let peer_features = new_features(&reserved);
    reserved_clear_known_bits(&mut reserved);
    if reserved != [0u8; RESERVED_SIZE] {
        tracing::warn!(reserved = ?Hex(&reserved), "unknown reserved bits");
    }

    stream.recv_fill(INFO_HASH_SIZE).await?;
    {
        let buffer = stream.buffer();
        ensure!(
            buffer.starts_with(info_hash.as_ref()),
            error::ExpectInfoHashSnafu {
                info_hash: InfoHash::new(buffer[0..INFO_HASH_SIZE].try_into().unwrap()),
                expect: info_hash,
            },
        );
        buffer.advance(INFO_HASH_SIZE);
    }

    Ok(peer_features)
}

async fn send_handshake<Stream>(
    stream: &mut Stream,
    info_hash: InfoHash,
    self_features: Features,
) -> Result<(), Error>
where
    Stream: StreamSend<Error = Error>,
{
    {
        let mut buffer = stream.buffer();
        buffer.put_u8(PROTOCOL_ID.len().try_into().unwrap());
        buffer.put_slice(PROTOCOL_ID);
        buffer.put_slice(&new_reserved(self_features));
        buffer.put_slice(info_hash.as_ref());
    }
    stream.send_all().await
}

async fn recv_peer_id<Stream>(
    stream: &mut Stream,
    expect_peer_id: Option<PeerId>,
) -> Result<PeerId, Error>
where
    Stream: StreamRecv<Error = Error> + Send,
{
    stream.recv_fill(PEER_ID_SIZE).await?;
    let mut peer_id = [0u8; PEER_ID_SIZE];
    stream.buffer().copy_to_slice(&mut peer_id);
    let peer_id = PeerId::new(peer_id);
    if let Some(expect) = expect_peer_id {
        ensure!(
            peer_id == expect,
            error::ExpectPeerIdSnafu { peer_id, expect }
        );
    }
    Ok(peer_id)
}

async fn send_self_id<Stream>(stream: &mut Stream, self_id: PeerId) -> Result<(), Error>
where
    Stream: StreamSend<Error = Error>,
{
    stream.buffer().put_slice(self_id.as_ref());
    stream.send_all().await
}

fn new_reserved(features: Features) -> Reserved {
    let mut reserved = Reserved::default();
    let bits: &mut ReservedBits = reserved.view_bits_mut();
    bits.set(RESERVED_DHT, features.dht);
    bits.set(RESERVED_FAST, features.fast);
    bits.set(RESERVED_EXTENSION, features.extension);
    reserved
}

fn new_features(reserved: &Reserved) -> Features {
    let bits: &ReservedBits = reserved.view_bits();
    Features::new(
        bits[RESERVED_DHT],
        bits[RESERVED_FAST],
        bits[RESERVED_EXTENSION],
    )
}

fn reserved_clear_known_bits(reserved: &mut Reserved) {
    let bits: &mut ReservedBits = reserved.view_bits_mut();
    for offset in RESERVED_OFFSETS {
        bits.set(*offset, false);
    }
}

#[cfg(test)]
mod tests {
    use hex_literal::hex;
    use tokio::io::{self, AsyncReadExt, AsyncWriteExt};

    use g1_tokio::io::Stream;

    use super::*;

    #[tokio::test]
    async fn handshake() {
        async fn test(
            test_data: &[u8],
            self_features: Features,
            expect_result: Result<Features, error::Error>,
            expect_connect: &[u8],
            expect_accept: &[u8],
        ) {
            let info_hash = InfoHash::new(hex!("3333333333333333333333333333333333333333"));
            let self_id = PeerId::new(hex!("1111111111111111111111111111111111111111"));
            let peer_id = PeerId::new(hex!("2222222222222222222222222222222222222222"));

            macro_rules! do_test {
                ($handshake:ident, $expect:ident $(,)?) => {
                    let (mut stream, mut mock) = Stream::new_mock(4096);
                    mock.write_all(test_data).await.unwrap();

                    let result = $handshake(
                        &mut stream,
                        info_hash.clone(),
                        self_id.clone(),
                        self_features,
                        Some(peer_id.clone()),
                    )
                    .await
                    .map_err(|error| Box::into_inner(error.downcast::<error::Error>().unwrap()));
                    assert_eq!(
                        result,
                        expect_result
                            .clone()
                            .map(|peer_features| (peer_id.clone(), peer_features)),
                    );

                    drop(stream);
                    let mut data = Vec::new();
                    mock.read_to_end(&mut data).await.unwrap();
                    assert_eq!(data, $expect);
                };
            }

            do_test!(connect, expect_connect);
            do_test!(accept, expect_accept);
        }

        test(
            &hex!(
                "13"
                "42 69 74 54 6f 72 72 65 6e 74 20 70 72 6f 74 6f 63 6f 6c"
                "00 00 00 00 00 00 00 00"
                "3333333333333333333333333333333333333333"
                "2222222222222222222222222222222222222222"
            ),
            Features::new(false, false, false),
            Ok(Features::new(false, false, false)),
            &hex!(
                "13"
                "42 69 74 54 6f 72 72 65 6e 74 20 70 72 6f 74 6f 63 6f 6c"
                "00 00 00 00 00 00 00 00"
                "3333333333333333333333333333333333333333"
                "1111111111111111111111111111111111111111"
            ),
            &hex!(
                "13"
                "42 69 74 54 6f 72 72 65 6e 74 20 70 72 6f 74 6f 63 6f 6c"
                "00 00 00 00 00 00 00 00"
                "3333333333333333333333333333333333333333"
                "1111111111111111111111111111111111111111"
            ),
        )
        .await;
        test(
            &hex!(
                "13"
                "42 69 74 54 6f 72 72 65 6e 74 20 70 72 6f 74 6f 63 6f 6c"
                "00 00 00 00 00 00 00 04"
                "3333333333333333333333333333333333333333"
                "2222222222222222222222222222222222222222"
            ),
            Features::new(true, false, false),
            Ok(Features::new(false, true, false)),
            &hex!(
                "13"
                "42 69 74 54 6f 72 72 65 6e 74 20 70 72 6f 74 6f 63 6f 6c"
                "00 00 00 00 00 00 00 01"
                "3333333333333333333333333333333333333333"
                "1111111111111111111111111111111111111111"
            ),
            &hex!(
                "13"
                "42 69 74 54 6f 72 72 65 6e 74 20 70 72 6f 74 6f 63 6f 6c"
                "00 00 00 00 00 00 00 01"
                "3333333333333333333333333333333333333333"
                "1111111111111111111111111111111111111111"
            ),
        )
        .await;

        test(
            &hex!("00"),
            Features::new(false, false, false),
            Err(error::Error::ExpectProtocolIdSize {
                size: 0,
                expect: 19,
            }),
            &hex!(
                "13"
                "42 69 74 54 6f 72 72 65 6e 74 20 70 72 6f 74 6f 63 6f 6c"
                "00 00 00 00 00 00 00 00"
                "3333333333333333333333333333333333333333"
            ),
            &[],
        )
        .await;

        test(
            &hex!(
                "13"
                "61 61 61 61 61 61 61 61 61 61 61 61 61 61 61 61 61 61 61"
            ),
            Features::new(false, false, false),
            Err(error::Error::ExpectProtocolId {
                protocol_id: "aaaaaaaaaaaaaaaaaaa".to_string(),
                expect: "BitTorrent protocol".to_string(),
            }),
            &hex!(
                "13"
                "42 69 74 54 6f 72 72 65 6e 74 20 70 72 6f 74 6f 63 6f 6c"
                "00 00 00 00 00 00 00 00"
                "3333333333333333333333333333333333333333"
            ),
            &[],
        )
        .await;

        test(
            &hex!(
                "13"
                "42 69 74 54 6f 72 72 65 6e 74 20 70 72 6f 74 6f 63 6f 6c"
                "00 00 00 00 00 00 00 00"
                "4444444444444444444444444444444444444444"
            ),
            Features::new(false, false, false),
            Err(error::Error::ExpectInfoHash {
                info_hash: InfoHash::new(hex!("4444444444444444444444444444444444444444")),
                expect: InfoHash::new(hex!("3333333333333333333333333333333333333333")),
            }),
            &hex!(
                "13"
                "42 69 74 54 6f 72 72 65 6e 74 20 70 72 6f 74 6f 63 6f 6c"
                "00 00 00 00 00 00 00 00"
                "3333333333333333333333333333333333333333"
            ),
            &[],
        )
        .await;

        test(
            &hex!(
                "13"
                "42 69 74 54 6f 72 72 65 6e 74 20 70 72 6f 74 6f 63 6f 6c"
                "00 00 00 00 00 00 00 00"
                "3333333333333333333333333333333333333333"
                "4444444444444444444444444444444444444444"
            ),
            Features::new(false, false, false),
            Err(error::Error::ExpectPeerId {
                peer_id: PeerId::new(hex!("4444444444444444444444444444444444444444")),
                expect: PeerId::new(hex!("2222222222222222222222222222222222222222")),
            }),
            &hex!(
                "13"
                "42 69 74 54 6f 72 72 65 6e 74 20 70 72 6f 74 6f 63 6f 6c"
                "00 00 00 00 00 00 00 00"
                "3333333333333333333333333333333333333333"
                "1111111111111111111111111111111111111111"
            ),
            &hex!(
                "13"
                "42 69 74 54 6f 72 72 65 6e 74 20 70 72 6f 74 6f 63 6f 6c"
                "00 00 00 00 00 00 00 00"
                "3333333333333333333333333333333333333333"
                "1111111111111111111111111111111111111111"
            ),
        )
        .await;

        let (mut stream_a, mut mock_a) = Stream::new_mock(4096);
        let (mut stream_b, mut mock_b) = Stream::new_mock(4096);
        tokio::try_join!(
            async move {
                connect(
                    &mut stream_a,
                    InfoHash::new(hex!("3333333333333333333333333333333333333333")),
                    PeerId::new(hex!("1111111111111111111111111111111111111111")),
                    Features::new(false, false, false),
                    Some(PeerId::new(hex!(
                        "2222222222222222222222222222222222222222"
                    ))),
                )
                .await
            },
            async move {
                accept(
                    &mut stream_b,
                    InfoHash::new(hex!("3333333333333333333333333333333333333333")),
                    PeerId::new(hex!("2222222222222222222222222222222222222222")),
                    Features::new(false, false, false),
                    Some(PeerId::new(hex!(
                        "1111111111111111111111111111111111111111"
                    ))),
                )
                .await
            },
            async move { io::copy_bidirectional(&mut mock_a, &mut mock_b).await },
        )
        .unwrap();
    }

    #[test]
    fn reserved() {
        fn test(features: Features, reserved: Reserved) {
            assert_eq!(new_reserved(features), reserved);
            assert_eq!(new_features(&reserved), features);
        }

        test(
            Features::new(false, false, false),
            hex!("00 00 00 00 00 00 00 00"),
        );
        test(
            Features::new(true, false, false),
            hex!("00 00 00 00 00 00 00 01"),
        );
        test(
            Features::new(false, true, false),
            hex!("00 00 00 00 00 00 00 04"),
        );
        test(
            Features::new(false, false, true),
            hex!("00 00 00 00 00 10 00 00"),
        );

        assert_eq!(
            new_features(&hex!("ff ff ff ff ff ef ff fa")),
            Features::new(false, false, false),
        );

        let mut reserved = hex!("ff ff ff ff ff ff ff ff");
        reserved_clear_known_bits(&mut reserved);
        assert_eq!(reserved, hex!("7f ff f7 ff ff ec ff e0"));
    }
}
