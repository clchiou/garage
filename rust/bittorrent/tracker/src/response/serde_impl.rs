use std::collections::BTreeMap;
use std::net::{IpAddr, SocketAddr, SocketAddrV4, SocketAddrV6};
use std::time::Duration;

use snafu::prelude::*;

use bittorrent_base::{compact::Compact, PEER_ID_SIZE};
use bittorrent_bencode::{
    borrow,
    convert::{to_bytes, to_dict, to_int, to_str, to_vec},
    dict::DictionaryRemove,
    serde as serde_bencode,
};

use crate::error::{Error, InvalidPeerIdSnafu};

use super::{Endpoint, PeerContactInfo, Response};

const COMPLETE: &[u8] = b"complete";
const FAILURE_REASON: &[u8] = b"failure reason";
const INCOMPLETE: &[u8] = b"incomplete";
const INTERVAL: &[u8] = b"interval";
const MIN_INTERVAL: &[u8] = b"min interval";
const PEERS: &[u8] = b"peers";
const PEERS6: &[u8] = b"peers6"; // BEP 7 IPv6 Tracker Extension
const TRACKER_ID: &[u8] = b"tracker id";
const WARNING_MESSAGE: &[u8] = b"warning message";

const PEER_ID: &[u8] = b"peer id";
const IP: &[u8] = b"ip";
const PORT: &[u8] = b"port";

impl<'a> TryFrom<&'a [u8]> for Response<'a> {
    type Error = serde_bencode::Error;

    fn try_from(buffer: &'a [u8]) -> Result<Self, Self::Error> {
        serde_bencode::from_bytes(buffer)
    }
}

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for Response<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        // TODO: If "failure reason" is present, `dict` should not have any other entries; however,
        // for now, we do not check this.
        if let Some(reason) = dict.remove_str::<Error>(FAILURE_REASON)? {
            return Err(Error::Failure {
                reason: String::from(reason),
            });
        }
        let mut peers = dict.must_remove(PEERS).and_then(to_peers)?;
        if let Some(peers6) = dict.remove(PEERS6) {
            // TODO: Is there a `Vec::try_extend`?
            decode_peers::<SocketAddrV6>(to_bytes::<Error>(peers6)?)?.try_for_each(|result| {
                peers.push(result?);
                Ok::<_, Error>(())
            })?;
        }
        Ok(Self {
            warning_message: dict.remove_str::<Error>(WARNING_MESSAGE)?,
            interval: dict
                .must_remove(INTERVAL)
                .and_then(to_int)
                .and_then(to_interval)?,
            min_interval: dict
                .remove_int::<Error>(MIN_INTERVAL)?
                .map(to_interval)
                .transpose()?,
            tracker_id: dict.remove_str::<Error>(TRACKER_ID)?,
            complete: dict
                .remove_int::<Error>(COMPLETE)?
                .map(to_num_peers)
                .transpose()?,
            incomplete: dict
                .remove_int::<Error>(INCOMPLETE)?
                .map(to_num_peers)
                .transpose()?,
            peers,
            extra: dict,
        })
    }
}

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for PeerContactInfo<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        Ok(Self {
            id: dict
                .remove(PEER_ID)
                .map(|peer_id| to_bytes(peer_id).and_then(to_peer_id))
                .transpose()?,
            endpoint: Endpoint::from((
                dict.must_remove::<Error>(IP).and_then(to_str)?,
                dict.must_remove(PORT).and_then(to_int).and_then(to_port)?,
            )),
            extra: dict,
        })
    }
}

impl<'a> From<(&'a str, u16)> for Endpoint<'a> {
    fn from((address, port): (&'a str, u16)) -> Self {
        match address.parse::<IpAddr>() {
            Ok(address) => Self::SocketAddr((address, port).into()),
            Err(_) => Self::DomainName(address, port),
        }
    }
}

fn to_interval(interval: i64) -> Result<Duration, Error> {
    Ok(Duration::from_secs(
        interval
            .try_into()
            .map_err(|_| Error::InvalidInterval { interval })?,
    ))
}

fn to_num_peers(num_peers: i64) -> Result<u64, Error> {
    num_peers
        .try_into()
        .map_err(|_| Error::InvalidNumPeers { num_peers })
}

fn to_peers(value: borrow::Value) -> Result<Vec<PeerContactInfo>, Error> {
    match value {
        borrow::Value::ByteString(_) => {
            decode_peers::<SocketAddrV4>(to_bytes::<Error>(value)?)?.try_collect()
        }
        borrow::Value::List(_) => to_vec(value, |peer| to_dict::<Error>(peer)?.0.try_into()),
        _ => Err(Error::InvalidPeerList {
            peers: value.to_owned(),
        }),
    }
}

fn decode_peers<'a, T>(
    peers: &'a [u8],
) -> Result<impl Iterator<Item = Result<PeerContactInfo<'a>, Error>> + 'a, Error>
where
    T: Compact + 'a,
    SocketAddr: From<T>,
{
    Ok(T::decode_many(peers)?.map(|result| Ok(SocketAddr::from(result?).into())))
}

fn to_peer_id(peer_id: &[u8]) -> Result<&[u8], Error> {
    ensure!(
        peer_id.len() == PEER_ID_SIZE,
        InvalidPeerIdSnafu {
            peer_id: peer_id.escape_ascii().to_string(),
        },
    );
    Ok(peer_id)
}

fn to_port(port: i64) -> Result<u16, Error> {
    port.try_into().map_err(|_| Error::InvalidPort { port })
}

#[cfg(test)]
mod tests {
    use hex_literal::hex;

    use super::*;

    fn new_bytes(bytes: &[u8]) -> borrow::Value<'_> {
        borrow::Value::new_byte_string(bytes)
    }

    fn new_btree_map<'a, const N: usize>(
        data: [(&'a [u8], borrow::Value<'a>); N],
    ) -> BTreeMap<&'a [u8], borrow::Value<'a>> {
        BTreeMap::from(data)
    }

    #[test]
    fn failure() {
        assert_eq!(
            Response::try_from(new_btree_map([(b"failure reason", new_bytes(b"xyz"))])),
            Err(Error::Failure {
                reason: String::from("xyz"),
            }),
        );
    }

    #[test]
    fn response() {
        assert_eq!(
            Response::try_from(new_btree_map([
                (b"warning message", new_bytes(b"xyz")),
                (b"interval", 1.into()),
                (b"min interval", 2.into()),
                (b"tracker id", new_bytes(b"abc")),
                (b"complete", 3.into()),
                (b"incomplete", 4.into()),
                (b"peers", new_bytes(&[127, 0, 0, 1, 0x12, 0x34])),
                (
                    b"peers6",
                    new_bytes(&hex!(
                        "10010000000000000000000000000001 5678"
                        "20020000000000000000000000000002 90ab"
                    )),
                ),
                (b"x", 5.into()),
            ])),
            Ok(Response {
                warning_message: Some("xyz"),
                interval: Duration::from_secs(1),
                min_interval: Some(Duration::from_secs(2)),
                tracker_id: Some("abc"),
                complete: Some(3),
                incomplete: Some(4),
                peers: vec![
                    PeerContactInfo {
                        id: None,
                        endpoint: Endpoint::SocketAddr("127.0.0.1:4660".parse().unwrap()),
                        extra: new_btree_map([]),
                    },
                    PeerContactInfo {
                        id: None,
                        endpoint: Endpoint::SocketAddr("[1001::1]:22136".parse().unwrap()),
                        extra: new_btree_map([]),
                    },
                    PeerContactInfo {
                        id: None,
                        endpoint: Endpoint::SocketAddr("[2002::2]:37035".parse().unwrap()),
                        extra: new_btree_map([]),
                    },
                ],
                extra: new_btree_map([(b"x", 5.into())]),
            }),
        );
    }

    #[test]
    fn peer_contact_info() {
        assert_eq!(
            to_peers(
                vec![
                    new_btree_map([(b"ip", new_bytes(b"127.0.0.1")), (b"port", 8000.into())])
                        .into(),
                    new_btree_map([(b"ip", new_bytes(b"::1")), (b"port", 8000.into())]).into(),
                    new_btree_map([(b"ip", new_bytes(b"localhost")), (b"port", 9000.into())])
                        .into(),
                ]
                .into()
            ),
            Ok(vec![
                PeerContactInfo {
                    id: None,
                    endpoint: Endpoint::SocketAddr("127.0.0.1:8000".parse().unwrap()),
                    extra: new_btree_map([]),
                },
                PeerContactInfo {
                    id: None,
                    endpoint: Endpoint::SocketAddr("[::1]:8000".parse().unwrap()),
                    extra: new_btree_map([]),
                },
                PeerContactInfo {
                    id: None,
                    endpoint: Endpoint::DomainName("localhost", 9000),
                    extra: new_btree_map([]),
                },
            ]),
        );
        assert_eq!(
            to_peers(new_bytes(&hex!("7f000001 1234 7f000002 5678"))),
            Ok(vec![
                PeerContactInfo {
                    id: None,
                    endpoint: Endpoint::SocketAddr("127.0.0.1:4660".parse().unwrap()),
                    extra: new_btree_map([]),
                },
                PeerContactInfo {
                    id: None,
                    endpoint: Endpoint::SocketAddr("127.0.0.2:22136".parse().unwrap()),
                    extra: new_btree_map([]),
                },
            ]),
        );

        assert_eq!(
            PeerContactInfo::try_from(new_btree_map([
                (b"peer id", new_bytes(b"01234567890123456789")),
                (b"ip", new_bytes(b"127.0.0.1")),
                (b"port", 8000.into()),
                (b"y", 1.into()),
            ])),
            Ok(PeerContactInfo {
                id: Some(b"01234567890123456789"),
                endpoint: Endpoint::SocketAddr("127.0.0.1:8000".parse().unwrap()),
                extra: new_btree_map([(b"y", 1.into())]),
            }),
        );
        assert_eq!(
            PeerContactInfo::try_from(new_btree_map([
                (b"peer id", new_bytes(b"x")),
                (b"ip", new_bytes(b"127.0.0.1")),
                (b"port", 8000.into()),
                (b"y", 1.into()),
            ])),
            Err(Error::InvalidPeerId {
                peer_id: String::from("x"),
            }),
        );
    }

    #[test]
    fn endpoint() {
        assert_eq!(
            Endpoint::from(("127.0.0.1", 80)),
            Endpoint::SocketAddr("127.0.0.1:80".parse().unwrap()),
        );
        assert_eq!(
            Endpoint::from(("::1", 80)),
            Endpoint::SocketAddr("[::1]:80".parse().unwrap()),
        );
        assert_eq!(
            Endpoint::from(("localhost", 80)),
            Endpoint::DomainName("localhost", 80),
        );
    }

    #[test]
    fn test_to_interval() {
        assert_eq!(to_interval(0), Ok(Duration::from_secs(0)));
        assert_eq!(to_interval(1), Ok(Duration::from_secs(1)));
        assert_eq!(
            to_interval(-1),
            Err(Error::InvalidInterval { interval: -1 }),
        );
    }

    #[test]
    fn test_to_num_peers() {
        assert_eq!(to_num_peers(0), Ok(0));
        assert_eq!(to_num_peers(1), Ok(1));
        assert_eq!(
            to_num_peers(-1),
            Err(Error::InvalidNumPeers { num_peers: -1 }),
        );
    }

    #[test]
    fn test_to_port() {
        assert_eq!(to_port(0), Ok(0));
        assert_eq!(to_port(1), Ok(1));
        assert_eq!(to_port(65535), Ok(65535));
        assert_eq!(to_port(-1), Err(Error::InvalidPort { port: -1 }),);
        assert_eq!(to_port(65536), Err(Error::InvalidPort { port: 65536 }),);
    }
}
