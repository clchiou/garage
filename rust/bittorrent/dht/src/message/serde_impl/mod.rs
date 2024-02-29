mod convert;
mod query;
mod response;

use std::collections::BTreeMap;

use serde_bytes::Bytes;

use bittorrent_bencode::{
    borrow,
    convert::{from_bytes, from_dict, to_bytes},
    dict::{DictionaryInsert, DictionaryRemove},
    own,
};

use crate::message::{
    query::Query,
    response::{Error as ErrorResponse, Response},
    Error, Message, Payload,
};

const TXID: &[u8] = b"t";
const MESSAGE_TYPE: &[u8] = b"y";
const VERSION: &[u8] = b"v";

const QUERY: &[u8] = b"q";
const RESPONSE: &[u8] = b"r";
const ERROR: &[u8] = b"e";

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for Message<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        Ok(Self {
            txid: dict.must_remove(TXID).and_then(to_bytes::<Error>)?,
            payload: Payload::try_from(&mut dict)?,
            version: dict.remove(VERSION).map(to_bytes::<Error>).transpose()?,
            extra: dict,
        })
    }
}

impl<'a> From<Message<'a>> for BTreeMap<&'a Bytes, own::Value> {
    fn from(message: Message<'a>) -> Self {
        let mut dict = Self::from(message.payload);
        dict.insert_from(TXID, Some(message.txid), from_bytes);
        dict.insert_from(VERSION, message.version, from_bytes);
        dict.append(&mut from_dict(message.extra, Bytes::new));
        dict
    }
}

impl<'a> TryFrom<&mut BTreeMap<&'a [u8], borrow::Value<'a>>> for Payload<'a> {
    type Error = Error;

    fn try_from(dict: &mut BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Error> {
        let message_type = dict.must_remove::<Error>(MESSAGE_TYPE).and_then(to_bytes)?;
        match message_type {
            QUERY => Ok(Payload::Query(Query::try_from(dict)?)),
            RESPONSE => Ok(Payload::Response(Response::try_from(dict)?)),
            ERROR => Ok(Payload::Error(ErrorResponse::try_from(dict)?)),
            _ => Err(Error::UnknownMessageType {
                message_type: message_type.into(),
            }),
        }
    }
}

impl<'a> From<Payload<'a>> for BTreeMap<&'a Bytes, own::Value> {
    fn from(payload: Payload<'a>) -> Self {
        let (mut dict, message_type) = match payload {
            Payload::Query(query) => (Self::from(query), QUERY),
            Payload::Response(response) => (Self::from(response), RESPONSE),
            Payload::Error(error) => (Self::from(error), ERROR),
        };
        assert_eq!(
            dict.insert(Bytes::new(MESSAGE_TYPE), from_bytes(message_type)),
            None,
        );
        dict
    }
}

#[cfg(test)]
mod test_harness {
    use std::fmt;

    use super::*;

    pub(super) const TEST_ID: &[u8] = b"0123456789abcdef0123";

    impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for Payload<'a> {
        type Error = Error;

        fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Error> {
            Self::try_from(&mut dict)
        }
    }

    pub(super) fn new_bytes(bytes: &[u8]) -> borrow::Value<'_> {
        borrow::Value::new_byte_string(bytes)
    }

    pub(super) fn new_btree_map<'a, const N: usize>(
        data: [(&'a [u8], borrow::Value<'a>); N],
    ) -> BTreeMap<&'a [u8], borrow::Value<'a>> {
        BTreeMap::from(data)
    }

    pub(super) fn test_ok<'a, T, const N: usize>(
        data: [(&'a [u8], borrow::Value<'a>); N],
        expect: T,
    ) where
        T: Clone + fmt::Debug + PartialEq + 'a,
        T: TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>, Error = Error>,
        T: Into<BTreeMap<&'a Bytes, own::Value>>,
    {
        let dict = BTreeMap::from(data);
        assert_eq!(T::try_from(dict.clone()), Ok(expect.clone()));
        assert_eq!(
            expect.into(),
            dict.into_iter()
                .map(|(k, v)| (Bytes::new(k), v.to_owned()))
                .collect()
        );
    }

    pub(super) fn test_err<'a, T, const N: usize>(
        data: [(&'a [u8], borrow::Value<'a>); N],
        error: Error,
    ) where
        T: fmt::Debug + PartialEq + 'a,
        T: TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>, Error = Error>,
    {
        assert_eq!(T::try_from(BTreeMap::from(data)), Err(error));
    }
}

#[cfg(test)]
mod tests {
    use crate::message::{query, response};

    use super::{test_harness::*, *};

    #[test]
    fn message() {
        test_ok(
            [
                (b"t", new_bytes(b"\x01\x02")),
                (b"y", new_bytes(b"q")),
                (b"q", new_bytes(b"ping")),
                (
                    b"a",
                    new_btree_map([(b"id", new_bytes(TEST_ID)), (b"spam egg", 1.into())]).into(),
                ),
                (b"v", new_bytes(b"some version")),
                (b"foo bar", 0.into()),
            ],
            Message {
                txid: b"\x01\x02",
                payload: Payload::Query(query::Query::Ping(query::Ping {
                    id: TEST_ID,
                    extra: new_btree_map([(b"spam egg", 1.into())]),
                })),
                version: Some(b"some version"),
                extra: new_btree_map([(b"foo bar", 0.into())]),
            },
        );
    }

    #[test]
    fn payload() {
        test_ok(
            [
                (b"y", new_bytes(b"r")),
                (
                    b"r",
                    new_btree_map([(b"id", new_bytes(TEST_ID)), (b"spam egg", 1.into())]).into(),
                ),
                (b"ip", new_bytes(b"some ip")),
            ],
            Payload::Response(response::Response {
                response: new_btree_map([(b"id", new_bytes(TEST_ID)), (b"spam egg", 1.into())]),
                requester: Some(b"some ip"),
            }),
        );
        test_ok(
            [
                (b"y", new_bytes(b"e")),
                (b"e", vec![201.into(), new_bytes(b"foo bar")].into()),
            ],
            Payload::Error(response::Error::GenericError { message: "foo bar" }),
        );
        test_err::<Payload, _>(
            [(b"y", new_bytes(b"no-such-type"))],
            Error::UnknownMessageType {
                message_type: b"no-such-type".to_vec(),
            },
        );
    }
}
