use std::collections::BTreeMap;

use serde_bytes::Bytes;
use snafu::prelude::*;

use bittorrent_bencode::{
    borrow,
    convert::{from_bytes, from_dict, from_str, to_bytes, to_dict, to_int, to_str, to_vec},
    dict::{DictionaryInsert, DictionaryRemove},
    own,
};

use crate::message::{
    response::{AnnouncePeer, Error as ErrorResponse, FindNode, GetPeers, Ping, Response},
    Error, ExpectErrorListSizeSnafu, MissingDictionaryKeySnafu,
};

use super::{convert::to_id, ERROR, RESPONSE};

const ID: &[u8] = b"id";
const TOKEN: &[u8] = b"token";
const NODES: &[u8] = b"nodes";
const VALUES: &[u8] = b"values";
const REQUESTER: &[u8] = b"ip"; // BEP 42 DHT Security Extension

const GENERIC_ERROR: i64 = 201;
const SERVER_ERROR: i64 = 202;
const PROTOCOL_ERROR: i64 = 203;
const METHOD_UNKNOWN: i64 = 204;

impl<'a> TryFrom<&mut BTreeMap<&'a [u8], borrow::Value<'a>>> for Response<'a> {
    type Error = Error;

    fn try_from(dict: &mut BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        // The implementation of BEP 42 in libtorrent also appears to send back our external IP
        // address and port in "ip" and "p" of the response dictionary.  However, BEP 42 does not
        // specify this behavior.  For now, we ignore them.
        let (response, _) = dict.must_remove::<Error>(RESPONSE).and_then(to_dict)?;
        Ok(Self {
            response,
            requester: dict.remove(REQUESTER).map(to_bytes::<Error>).transpose()?,
        })
    }
}

impl<'a> From<Response<'a>> for BTreeMap<&'a Bytes, own::Value> {
    fn from(response: Response<'a>) -> Self {
        let mut dict = Self::from([(
            Bytes::new(RESPONSE),
            from_dict(response.response, own::ByteString::from).into(),
        )]);
        dict.insert_from(REQUESTER, response.requester, from_bytes);
        dict
    }
}

impl<'a> TryFrom<Response<'a>> for Ping<'a> {
    type Error = Error;

    fn try_from(response: Response<'a>) -> Result<Self, Self::Error> {
        response.response.try_into()
    }
}

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for Ping<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        Ok(Self {
            id: dict.must_remove(ID).and_then(to_id)?,
            extra: dict,
        })
    }
}

impl<'a> From<Ping<'a>> for BTreeMap<&'a [u8], borrow::Value<'a>> {
    fn from(mut ping: Ping<'a>) -> Self {
        let mut dict = Self::from([(ID, borrow::Value::ByteString(ping.id))]);
        dict.append(&mut ping.extra);
        dict
    }
}

impl<'a> TryFrom<Response<'a>> for FindNode<'a> {
    type Error = Error;

    fn try_from(response: Response<'a>) -> Result<Self, Self::Error> {
        response.response.try_into()
    }
}

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for FindNode<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        Ok(Self {
            id: dict.must_remove(ID).and_then(to_id)?,
            nodes: dict.must_remove::<Error>(NODES).and_then(to_bytes)?,
            extra: dict,
        })
    }
}

impl<'a> From<FindNode<'a>> for BTreeMap<&'a [u8], borrow::Value<'a>> {
    fn from(mut find_node: FindNode<'a>) -> Self {
        let mut dict = Self::from([
            (ID, borrow::Value::ByteString(find_node.id)),
            (NODES, borrow::Value::ByteString(find_node.nodes)),
        ]);
        dict.append(&mut find_node.extra);
        dict
    }
}

impl<'a> TryFrom<Response<'a>> for GetPeers<'a> {
    type Error = Error;

    fn try_from(response: Response<'a>) -> Result<Self, Self::Error> {
        response.response.try_into()
    }
}

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for GetPeers<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        let this = Self {
            id: dict.must_remove(ID).and_then(to_id)?,
            token: dict.remove(TOKEN).map(to_bytes::<Error>).transpose()?,
            values: dict
                .remove(VALUES)
                .map(|values| to_vec(values, to_bytes::<Error>))
                .transpose()?,
            nodes: dict.remove(NODES).map(to_bytes::<Error>).transpose()?,
            extra: dict,
        };
        ensure!(
            this.values.is_some() || this.nodes.is_some(),
            MissingDictionaryKeySnafu {
                key: "values or nodes",
            },
        );
        if this.values.is_some() {
            ensure!(
                this.token.is_some(),
                MissingDictionaryKeySnafu { key: "token" },
            );
        }
        Ok(this)
    }
}

impl<'a> From<GetPeers<'a>> for BTreeMap<&'a [u8], borrow::Value<'a>> {
    fn from(mut get_peers: GetPeers<'a>) -> Self {
        let mut dict = Self::from([(ID, borrow::Value::ByteString(get_peers.id))]);
        if let Some(token) = get_peers.token {
            dict.insert(TOKEN, borrow::Value::ByteString(token));
        }
        if let Some(values) = get_peers.values {
            dict.insert(
                VALUES,
                borrow::Value::new_list_without_raw_value(
                    values.into_iter().map(borrow::Value::ByteString).collect(),
                ),
            );
        }
        if let Some(nodes) = get_peers.nodes {
            dict.insert(NODES, borrow::Value::ByteString(nodes));
        }
        dict.append(&mut get_peers.extra);
        dict
    }
}

impl<'a> TryFrom<Response<'a>> for AnnouncePeer<'a> {
    type Error = Error;

    fn try_from(response: Response<'a>) -> Result<Self, Self::Error> {
        response.response.try_into()
    }
}

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for AnnouncePeer<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        Ok(Self {
            id: dict.must_remove(ID).and_then(to_id)?,
            extra: dict,
        })
    }
}

impl<'a> From<AnnouncePeer<'a>> for BTreeMap<&'a [u8], borrow::Value<'a>> {
    fn from(mut announce_peer: AnnouncePeer<'a>) -> Self {
        let mut dict = Self::from([(ID, borrow::Value::ByteString(announce_peer.id))]);
        dict.append(&mut announce_peer.extra);
        dict
    }
}

impl<'a> TryFrom<&mut BTreeMap<&'a [u8], borrow::Value<'a>>> for ErrorResponse<'a> {
    type Error = Error;

    fn try_from(dict: &mut BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        // Some implementations appear to send a ping response along with the error response.  It
        // seems to me that BEP 5 does not specify this behavior.  Currently, this ping response is
        // stored in the `extra` field.
        let mut list = dict
            .must_remove::<Error>(ERROR)
            .and_then(|list| to_vec(list, Ok))?;
        ensure!(
            list.len() == 2,
            ExpectErrorListSizeSnafu { size: list.len() },
        );
        let message = to_str::<Error>(list.pop().unwrap())?;
        let error_code = to_int::<Error>(list.pop().unwrap())?;
        match error_code {
            GENERIC_ERROR => Ok(Self::GenericError { message }),
            SERVER_ERROR => Ok(Self::ServerError { message }),
            PROTOCOL_ERROR => Ok(Self::ProtocolError { message }),
            METHOD_UNKNOWN => Ok(Self::MethodUnknown { message }),
            _ => Err(Error::UnknownErrorCode { error_code }),
        }
    }
}

impl<'a> From<ErrorResponse<'a>> for BTreeMap<&'a Bytes, own::Value> {
    fn from(error: ErrorResponse<'a>) -> Self {
        let (error_code, message) = match error {
            ErrorResponse::GenericError { message } => (GENERIC_ERROR, message),
            ErrorResponse::ServerError { message } => (SERVER_ERROR, message),
            ErrorResponse::ProtocolError { message } => (PROTOCOL_ERROR, message),
            ErrorResponse::MethodUnknown { message } => (METHOD_UNKNOWN, message),
        };
        Self::from([(
            Bytes::new(ERROR),
            vec![error_code.into(), from_str(message)].into(),
        )])
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for Response<'a> {
        type Error = Error;

        fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Error> {
            Self::try_from(&mut dict)
        }
    }

    impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for ErrorResponse<'a> {
        type Error = Error;

        fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Error> {
            Self::try_from(&mut dict)
        }
    }
}

#[cfg(test)]
mod tests {
    use std::fmt;

    use super::{super::test_harness::*, *};

    #[test]
    fn response() {
        test_ok(
            [(b"r", BTreeMap::new().into())],
            Response {
                response: new_btree_map([]),
                requester: None,
            },
        );
    }

    #[test]
    fn response_body() {
        fn test_ok<'a, T, const N: usize>(data: [(&'a [u8], borrow::Value<'a>); N], expect: T)
        where
            T: Clone + fmt::Debug + PartialEq + 'a,
            T: TryFrom<Response<'a>, Error = Error>,
            T: TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>, Error = Error>,
            T: Into<BTreeMap<&'a [u8], borrow::Value<'a>>>,
        {
            let dict = BTreeMap::from(data);
            let response = Response {
                response: dict.clone(),
                requester: None,
            };
            assert_eq!(T::try_from(response), Ok(expect.clone()));
            assert_eq!(T::try_from(dict.clone()), Ok(expect.clone()));
            assert_eq!(expect.into(), dict);
        }

        test_ok(
            [(b"id", new_bytes(TEST_ID)), (b"foo bar", 0.into())],
            Ping {
                id: TEST_ID,
                extra: new_btree_map([(b"foo bar", 0.into())]),
            },
        );

        test_ok(
            [
                (b"id", new_bytes(TEST_ID)),
                (b"nodes", new_bytes(b"some nodes")),
                (b"foo bar", 0.into()),
            ],
            FindNode {
                id: TEST_ID,
                nodes: b"some nodes",
                extra: new_btree_map([(b"foo bar", 0.into())]),
            },
        );

        test_ok(
            [
                (b"id", new_bytes(TEST_ID)),
                (b"token", new_bytes(b"some token")),
                (b"values", vec![new_bytes(b"v0"), new_bytes(b"v1")].into()),
                (b"nodes", new_bytes(b"some nodes")),
                (b"foo bar", 0.into()),
            ],
            GetPeers {
                id: TEST_ID,
                token: Some(b"some token"),
                values: Some(vec![b"v0", b"v1"]),
                nodes: Some(b"some nodes"),
                extra: new_btree_map([(b"foo bar", 0.into())]),
            },
        );
        test_err::<GetPeers, _>(
            [
                (b"id", new_bytes(TEST_ID)),
                (b"token", new_bytes(b"some token")),
                (b"foo bar", 0.into()),
            ],
            Error::MissingDictionaryKey {
                key: "values or nodes".to_string(),
            },
        );
        test_err::<GetPeers, _>(
            [
                (b"id", new_bytes(TEST_ID)),
                (b"values", vec![new_bytes(b"v0"), new_bytes(b"v1")].into()),
                (b"foo bar", 0.into()),
            ],
            Error::MissingDictionaryKey {
                key: "token".to_string(),
            },
        );

        test_ok(
            [(b"id", new_bytes(TEST_ID)), (b"foo bar", 0.into())],
            AnnouncePeer {
                id: TEST_ID,
                extra: new_btree_map([(b"foo bar", 0.into())]),
            },
        );
    }

    #[test]
    fn error() {
        test_ok(
            [(b"e", vec![201.into(), new_bytes(b"foo bar")].into())],
            ErrorResponse::GenericError { message: "foo bar" },
        );
        test_ok(
            [(b"e", vec![202.into(), new_bytes(b"foo bar")].into())],
            ErrorResponse::ServerError { message: "foo bar" },
        );
        test_ok(
            [(b"e", vec![203.into(), new_bytes(b"foo bar")].into())],
            ErrorResponse::ProtocolError { message: "foo bar" },
        );
        test_ok(
            [(b"e", vec![204.into(), new_bytes(b"foo bar")].into())],
            ErrorResponse::MethodUnknown { message: "foo bar" },
        );
        test_err::<ErrorResponse, _>(
            [(b"e", vec![200.into(), new_bytes(b"foo bar")].into())],
            Error::UnknownErrorCode { error_code: 200 },
        );
        test_err::<ErrorResponse, _>(
            [(b"e", vec![205.into(), new_bytes(b"foo bar")].into())],
            Error::UnknownErrorCode { error_code: 205 },
        );
    }
}
