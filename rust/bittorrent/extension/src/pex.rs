use std::collections::BTreeMap;
use std::iter;
use std::net::{SocketAddr, SocketAddrV4, SocketAddrV6};

use bitvec::prelude::*;
use bytes::{BufMut, BytesMut};
use serde::{Deserialize, Serialize};
use serde_bytes::Bytes;
use snafu::prelude::*;

use g1_base::fmt::{DebugExt, Hex};

use bittorrent_base::compact::Compact;
use bittorrent_bencode::{
    borrow,
    convert::{from_bytes, from_dict, to_bytes},
    own, serde as serde_bencode, FormatDictionary,
};

use crate::{Error, ExpectPeerExchangeEndpointsSizeSnafu};

g1_param::define!(pub(crate) enable: bool = true); // BEP 11

//
// Implementer's Notes: we currently treat "not present" the same as "present but empty".
//

#[derive(Clone, DebugExt, Deserialize, Eq, PartialEq, Serialize)]
#[serde(
    try_from = "BTreeMap<&[u8], borrow::Value>",
    into = "BTreeMap<&Bytes, own::Value>"
)]
pub struct PeerExchange<'a> {
    #[debug(with = Hex)]
    added_v4: &'a [u8],
    #[debug(with = Hex)]
    added_v6: &'a [u8],
    #[debug(with = Hex)]
    added_flags_v4: &'a [u8],
    #[debug(with = Hex)]
    added_flags_v6: &'a [u8],
    #[debug(with = Hex)]
    dropped_v4: &'a [u8],
    #[debug(with = Hex)]
    dropped_v6: &'a [u8],

    #[debug(with = FormatDictionary)]
    pub extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub struct PeerContactInfo {
    pub endpoint: SocketAddr,
    flags: u8,
}

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
#[repr(usize)]
pub enum PeerFlag {
    PreferEncryption = 7,
    UploadOnly = 6,
    SupportUtp = 5,
    SupportHolepunch = 4,
    Reachable = 3,
}

impl<'a> PeerExchange<'a> {
    // TODO: How can we make this id value match the global `EXTENSIONS` array index?
    pub const ID: u8 = 2;

    pub fn new(
        added_v4: &'a [u8],
        added_v6: &'a [u8],
        added_flags_v4: &'a [u8],
        added_flags_v6: &'a [u8],
        dropped_v4: &'a [u8],
        dropped_v6: &'a [u8],
    ) -> Self {
        Self {
            added_v4,
            added_v6,
            added_flags_v4,
            added_flags_v6,
            dropped_v4,
            dropped_v6,
            extra: BTreeMap::new(),
        }
    }

    pub fn decode_added_v4(
        &self,
    ) -> Result<impl Iterator<Item = PeerContactInfo> + use<'a>, Error> {
        Ok(
            decode_endpoints::<SocketAddrV4>(self.added_v4, self.added_flags_v4.len())?
                .zip(self.added_flags_v4.iter().copied().chain(iter::repeat(0)))
                // For now, we do not check for unrecognizable peer bit flags.
                .map(|(endpoint, flags)| PeerContactInfo { endpoint, flags }),
        )
    }

    pub fn decode_added_v6(
        &self,
    ) -> Result<impl Iterator<Item = PeerContactInfo> + use<'a>, Error> {
        Ok(
            decode_endpoints::<SocketAddrV6>(self.added_v6, self.added_flags_v6.len())?
                .zip(self.added_flags_v6.iter().copied().chain(iter::repeat(0)))
                // For now, we do not check for unrecognizable peer bit flags.
                .map(|(endpoint, flags)| PeerContactInfo { endpoint, flags }),
        )
    }

    pub fn decode_dropped_v4(&self) -> Result<impl Iterator<Item = SocketAddr> + use<'a>, Error> {
        decode_endpoints::<SocketAddrV4>(self.dropped_v4, 0)
    }

    pub fn decode_dropped_v6(&self) -> Result<impl Iterator<Item = SocketAddr> + use<'a>, Error> {
        decode_endpoints::<SocketAddrV6>(self.dropped_v6, 0)
    }

    pub fn encode(
        added: impl Iterator<Item = PeerContactInfo>,
        dropped: impl Iterator<Item = SocketAddr>,
        buffer: &mut impl BufMut,
    ) {
        let (added_v4, added_v6, added_flags_v4, added_flags_v6) = Self::encode_added(added);
        let (dropped_v4, dropped_v6) = Self::encode_dropped(dropped);
        // It must be `PeerExchange::new` and cannot be `Self::new` due to the lifetime bound `'a`.
        let this = PeerExchange::new(
            &added_v4,
            &added_v6,
            &added_flags_v4,
            &added_flags_v6,
            &dropped_v4,
            &dropped_v6,
        );
        this.serialize(serde_bencode::Serializer)
            .unwrap()
            .encode(buffer);
    }

    pub fn encode_added(
        peers: impl Iterator<Item = PeerContactInfo>,
    ) -> (bytes::Bytes, bytes::Bytes, bytes::Bytes, bytes::Bytes) {
        let mut added_v4 = BytesMut::new();
        let mut added_v6 = BytesMut::new();
        let mut added_flags_v4 = BytesMut::new();
        let mut added_flags_v6 = BytesMut::new();
        for peer in peers {
            match peer.endpoint {
                SocketAddr::V4(endpoint) => {
                    endpoint.encode(&mut added_v4);
                    added_flags_v4.put_u8(peer.flags);
                }
                SocketAddr::V6(endpoint) => {
                    endpoint.encode(&mut added_v6);
                    added_flags_v6.put_u8(peer.flags);
                }
            }
        }
        (
            added_v4.freeze(),
            added_v6.freeze(),
            added_flags_v4.freeze(),
            added_flags_v6.freeze(),
        )
    }

    pub fn encode_dropped(
        endpoints: impl Iterator<Item = SocketAddr>,
    ) -> (bytes::Bytes, bytes::Bytes) {
        let mut dropped_v4 = BytesMut::new();
        let mut dropped_v6 = BytesMut::new();
        for endpoint in endpoints {
            match endpoint {
                SocketAddr::V4(endpoint) => endpoint.encode(&mut dropped_v4),
                SocketAddr::V6(endpoint) => endpoint.encode(&mut dropped_v6),
            }
        }
        (dropped_v4.freeze(), dropped_v6.freeze())
    }
}

impl PeerContactInfo {
    pub fn new(endpoint: SocketAddr, set_flags: impl Iterator<Item = PeerFlag>) -> Self {
        let mut flags = 0u8;
        let bits = flags.view_bits_mut::<Msb0>();
        for set_flag in set_flags {
            bits.set(set_flag as usize, true);
        }
        Self { endpoint, flags }
    }

    pub fn get_flag(&self, flag: PeerFlag) -> bool {
        self.flags.view_bits::<Msb0>()[flag as usize]
    }

    pub fn set_flag(&mut self, flag: PeerFlag, value: bool) {
        self.flags.view_bits_mut::<Msb0>().set(flag as usize, value);
    }
}

const ADDED_V4: &[u8] = b"added";
const ADDED_V6: &[u8] = b"added6";
const ADDED_FLAGS_V4: &[u8] = b"added.f";
const ADDED_FLAGS_V6: &[u8] = b"added6.f";
const DROPPED_V4: &[u8] = b"dropped";
const DROPPED_V6: &[u8] = b"dropped6";

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for PeerExchange<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        Ok(Self {
            added_v4: remove_bytes(&mut dict, ADDED_V4)?,
            added_v6: remove_bytes(&mut dict, ADDED_V6)?,
            added_flags_v4: remove_bytes(&mut dict, ADDED_FLAGS_V4)?,
            added_flags_v6: remove_bytes(&mut dict, ADDED_FLAGS_V6)?,
            dropped_v4: remove_bytes(&mut dict, DROPPED_V4)?,
            dropped_v6: remove_bytes(&mut dict, DROPPED_V6)?,
            extra: dict,
        })
    }
}

impl<'a> From<PeerExchange<'a>> for BTreeMap<&'a Bytes, own::Value> {
    fn from(peer_exchange: PeerExchange<'a>) -> Self {
        let mut dict = from_dict(peer_exchange.extra, Bytes::new);
        insert_bytes(&mut dict, ADDED_V4, peer_exchange.added_v4);
        insert_bytes(&mut dict, ADDED_V6, peer_exchange.added_v6);
        insert_bytes(&mut dict, ADDED_FLAGS_V4, peer_exchange.added_flags_v4);
        insert_bytes(&mut dict, ADDED_FLAGS_V6, peer_exchange.added_flags_v6);
        insert_bytes(&mut dict, DROPPED_V4, peer_exchange.dropped_v4);
        insert_bytes(&mut dict, DROPPED_V6, peer_exchange.dropped_v6);
        dict
    }
}

fn decode_endpoints<'a, T>(
    endpoints: &'a [u8],
    expect: usize,
) -> Result<impl Iterator<Item = SocketAddr> + use<'a, T>, Error>
where
    T: Compact + 'a,
    SocketAddr: From<T>,
{
    let expect = expect * T::SIZE;
    ensure!(
        expect == 0 || expect == endpoints.len(),
        ExpectPeerExchangeEndpointsSizeSnafu {
            size: endpoints.len(),
            expect,
        },
    );
    Ok(T::decode_many(endpoints)
        .map_err(|_| Error::InvalidPeerExchangeEndpoints {
            endpoints: endpoints.to_vec(),
        })?
        // We can safely call `unwrap` because decoding an IPv4 or IPv6 address is guaranteed to
        // succeed.
        .map(|endpoint| endpoint.unwrap().into()))
}

fn remove_bytes<'a>(
    dict: &mut BTreeMap<&[u8], borrow::Value<'a>>,
    key: &[u8],
) -> Result<&'a [u8], Error> {
    Ok(dict
        .remove(key)
        .map(to_bytes::<Error>)
        .transpose()?
        .unwrap_or(&[]))
}

fn insert_bytes<'a>(dict: &mut BTreeMap<&'a Bytes, own::Value>, key: &'a [u8], bytes: &[u8]) {
    if !bytes.is_empty() {
        dict.insert(Bytes::new(key), from_bytes(bytes));
    }
}

#[cfg(test)]
mod tests {
    use hex_literal::hex;

    use super::*;

    #[test]
    fn id() {
        assert_eq!(
            crate::EXTENSIONS[usize::from(PeerExchange::ID)].name,
            "ut_pex",
        );
    }

    #[test]
    fn peer_flag() {
        fn test(set_flags: &[PeerFlag], expect: u8) {
            let peer =
                PeerContactInfo::new("127.0.0.1:8000".parse().unwrap(), set_flags.iter().copied());
            assert_eq!(peer.flags, expect);

            for flag in [
                PeerFlag::PreferEncryption,
                PeerFlag::UploadOnly,
                PeerFlag::SupportUtp,
                PeerFlag::SupportHolepunch,
                PeerFlag::Reachable,
            ] {
                assert_eq!(peer.get_flag(flag), set_flags.iter().any(|&f| f == flag));
            }
        }

        test(&[], 0x00);
        test(&[PeerFlag::PreferEncryption], 0x01);
        test(&[PeerFlag::UploadOnly], 0x02);
        test(&[PeerFlag::SupportUtp], 0x04);
        test(&[PeerFlag::SupportHolepunch], 0x08);
        test(&[PeerFlag::Reachable], 0x10);
        test(
            &[
                PeerFlag::PreferEncryption,
                PeerFlag::UploadOnly,
                PeerFlag::SupportUtp,
                PeerFlag::SupportHolepunch,
                PeerFlag::Reachable,
            ],
            0x1f,
        );
    }

    #[test]
    fn conversion() {
        fn test_serde(decode: BTreeMap<&[u8], borrow::Value>, peer_exchange: &PeerExchange) {
            let encode: BTreeMap<&Bytes, own::Value> = decode
                .iter()
                .map(|(key, value)| (Bytes::new(key), value.to_owned()))
                .collect();
            assert_eq!(PeerExchange::try_from(decode), Ok(peer_exchange.clone()));
            assert_eq!(BTreeMap::from(peer_exchange.clone()), encode);
        }

        fn test_decode(
            peer_exchange: &PeerExchange,
            added_v4: Vec<PeerContactInfo>,
            added_v6: Vec<PeerContactInfo>,
            dropped_v4: Vec<SocketAddr>,
            dropped_v6: Vec<SocketAddr>,
        ) {
            assert_eq!(
                peer_exchange.decode_added_v4().unwrap().collect::<Vec<_>>(),
                added_v4,
            );
            assert_eq!(
                peer_exchange.decode_added_v6().unwrap().collect::<Vec<_>>(),
                added_v6,
            );
            assert_eq!(
                peer_exchange
                    .decode_dropped_v4()
                    .unwrap()
                    .collect::<Vec<_>>(),
                dropped_v4,
            );
            assert_eq!(
                peer_exchange
                    .decode_dropped_v6()
                    .unwrap()
                    .collect::<Vec<_>>(),
                dropped_v6,
            );
        }

        fn bs(bytes: &[u8]) -> borrow::Value {
            borrow::Value::new_byte_string(bytes)
        }

        let peer_exchange = PeerExchange::new(&[], &[], &[], &[], &[], &[]);
        test_serde(BTreeMap::from([]), &peer_exchange);
        test_decode(
            &peer_exchange,
            Vec::new(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
        );

        test_serde(
            BTreeMap::from([(b"foo".as_slice(), bs(b"bar"))]),
            &PeerExchange {
                added_v4: &[],
                added_v6: &[],
                added_flags_v4: &[],
                added_flags_v6: &[],
                dropped_v4: &[],
                dropped_v6: &[],
                extra: BTreeMap::from([(b"foo".as_slice(), bs(b"bar"))]),
            },
        );

        let peer_exchange = PeerExchange::new(
            &hex!("7f000001 1f41"),
            &hex!("0000 0000 0000 0000 0000 0000 0000 0002 1f42"),
            &hex!("01"),
            &hex!("02"),
            &hex!("7f000003 1f43"),
            &hex!("0000 0000 0000 0000 0000 0000 0000 0004 1f44"),
        );
        test_serde(
            BTreeMap::from([
                (b"added".as_slice(), bs(&hex!("7f000001 1f41"))),
                (
                    b"added6".as_slice(),
                    bs(&hex!("0000 0000 0000 0000 0000 0000 0000 0002 1f42")),
                ),
                (b"added.f".as_slice(), bs(&hex!("01"))),
                (b"added6.f".as_slice(), bs(&hex!("02"))),
                (b"dropped".as_slice(), bs(&hex!("7f000003 1f43"))),
                (
                    b"dropped6".as_slice(),
                    bs(&hex!("0000 0000 0000 0000 0000 0000 0000 0004 1f44")),
                ),
            ]),
            &peer_exchange,
        );
        test_decode(
            &peer_exchange,
            vec![PeerContactInfo::new(
                "127.0.0.1:8001".parse().unwrap(),
                [PeerFlag::PreferEncryption].into_iter(),
            )],
            vec![PeerContactInfo::new(
                "[::2]:8002".parse().unwrap(),
                [PeerFlag::UploadOnly].into_iter(),
            )],
            vec!["127.0.0.3:8003".parse().unwrap()],
            vec!["[::4]:8004".parse().unwrap()],
        );

        test_decode(
            &PeerExchange::new(
                &hex!("7f000001 1f41"),
                &hex!("0000 0000 0000 0000 0000 0000 0000 0002 1f42"),
                &[],
                &[],
                &[],
                &[],
            ),
            vec![PeerContactInfo::new(
                "127.0.0.1:8001".parse().unwrap(),
                [].into_iter(),
            )],
            vec![PeerContactInfo::new(
                "[::2]:8002".parse().unwrap(),
                [].into_iter(),
            )],
            Vec::new(),
            Vec::new(),
        );
    }

    #[test]
    fn encode() {
        fn test(added: &[PeerContactInfo], dropped: &[SocketAddr], expect: &[u8]) {
            let mut buffer = BytesMut::new();
            PeerExchange::encode(added.iter().copied(), dropped.iter().copied(), &mut buffer);
            assert_eq!(buffer, expect);
        }

        fn concatenate(pieces: &[&[u8]]) -> bytes::Bytes {
            let mut buffer = BytesMut::new();
            for piece in pieces {
                buffer.put_slice(piece)
            }
            buffer.freeze()
        }

        test(&[], &[], b"de");
        test(
            &[
                PeerContactInfo::new("127.0.0.1:8001".parse().unwrap(), [].into_iter()),
                PeerContactInfo::new("[::2]:8002".parse().unwrap(), [].into_iter()),
                PeerContactInfo::new(
                    "127.0.0.3:8003".parse().unwrap(),
                    [PeerFlag::PreferEncryption].into_iter(),
                ),
                PeerContactInfo::new(
                    "[::4]:8004".parse().unwrap(),
                    [PeerFlag::UploadOnly].into_iter(),
                ),
            ],
            &[
                "127.0.0.5:8005".parse().unwrap(),
                "[::6]:8006".parse().unwrap(),
            ],
            &concatenate(&[
                b"d",
                b"5:added",
                b"12:\x7f\x00\x00\x01\x1f\x41\x7f\x00\x00\x03\x1f\x43",
                b"7:added.f",
                b"2:\x00\x01",
                b"6:added6",
                b"36:",
                b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x1f\x42",
                b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x04\x1f\x44",
                b"8:added6.f",
                b"2:\x00\x02",
                b"7:dropped",
                b"6:\x7f\x00\x00\x05\x1f\x45",
                b"8:dropped6",
                b"18:\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x06\x1f\x46",
                b"e",
            ]),
        );
    }

    #[test]
    fn test_decode_endpoints() {
        fn test_ok(endpoints: &[u8], expect: Vec<SocketAddr>) {
            assert_eq!(
                decode_endpoints::<SocketAddrV4>(endpoints, 0)
                    .unwrap()
                    .collect::<Vec<_>>(),
                expect,
            );
            assert_eq!(
                decode_endpoints::<SocketAddrV4>(endpoints, expect.len())
                    .unwrap()
                    .collect::<Vec<_>>(),
                expect,
            );
        }

        test_ok(&[], Vec::new());
        test_ok(
            &hex!("7f000001 1f40"),
            vec!["127.0.0.1:8000".parse().unwrap()],
        );
        test_ok(
            &hex!("7f000001 1f40 7f000002 1f41"),
            vec![
                "127.0.0.1:8000".parse().unwrap(),
                "127.0.0.2:8001".parse().unwrap(),
            ],
        );

        assert_eq!(
            decode_endpoints::<SocketAddrV4>(&hex!("7f000001"), 1).is_err_and(
                |error| error == Error::ExpectPeerExchangeEndpointsSize { size: 4, expect: 6 },
            ),
            true,
        );
        assert_eq!(
            decode_endpoints::<SocketAddrV4>(&hex!("7f000001"), 0).is_err_and(|error| error
                == Error::InvalidPeerExchangeEndpoints {
                    endpoints: hex!("7f000001").to_vec(),
                }),
            true,
        );
    }
}
