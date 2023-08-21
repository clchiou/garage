use bittorrent_bencode::serde as serde_bencode;

use crate::message::{response, Error, Message, Payload};

impl<'a> TryFrom<&'a [u8]> for Message<'a> {
    type Error = serde_bencode::Error;

    fn try_from(buffer: &'a [u8]) -> Result<Self, Self::Error> {
        serde_bencode::from_bytes(buffer)
    }
}

// Dummy `TryFrom` implementation, merely to satisfy `g1_base::define_owner`.
impl<'a> TryFrom<&'a [u8]> for response::Ping<'a> {
    type Error = ();

    fn try_from(_: &'a [u8]) -> Result<Self, Self::Error> {
        std::unreachable!()
    }
}

// Ditto.
impl<'a> TryFrom<&'a [u8]> for response::FindNode<'a> {
    type Error = ();

    fn try_from(_: &'a [u8]) -> Result<Self, Self::Error> {
        std::unreachable!()
    }
}

// Ditto.
impl<'a> TryFrom<&'a [u8]> for response::GetPeers<'a> {
    type Error = ();

    fn try_from(_: &'a [u8]) -> Result<Self, Self::Error> {
        std::unreachable!()
    }
}

// Ditto.
impl<'a> TryFrom<&'a [u8]> for response::AnnouncePeer<'a> {
    type Error = ();

    fn try_from(_: &'a [u8]) -> Result<Self, Self::Error> {
        std::unreachable!()
    }
}

impl<'a> TryFrom<Message<'a>> for response::Response<'a> {
    type Error = Error;

    fn try_from(message: Message<'a>) -> Result<Self, Self::Error> {
        match message.payload {
            Payload::Response(response) => Ok(response),
            Payload::Query(_) | Payload::Error(_) => Err(Error::ExpectResponse {
                message: format!("{:?}", message),
            }),
        }
    }
}

impl<'a> TryFrom<Message<'a>> for response::Ping<'a> {
    type Error = Error;

    fn try_from(message: Message<'a>) -> Result<Self, Self::Error> {
        response::Response::try_from(message).and_then(Self::try_from)
    }
}

impl<'a> TryFrom<Message<'a>> for response::FindNode<'a> {
    type Error = Error;

    fn try_from(message: Message<'a>) -> Result<Self, Self::Error> {
        response::Response::try_from(message).and_then(Self::try_from)
    }
}

impl<'a> TryFrom<Message<'a>> for response::GetPeers<'a> {
    type Error = Error;

    fn try_from(message: Message<'a>) -> Result<Self, Self::Error> {
        response::Response::try_from(message).and_then(Self::try_from)
    }
}

impl<'a> TryFrom<Message<'a>> for response::AnnouncePeer<'a> {
    type Error = Error;

    fn try_from(message: Message<'a>) -> Result<Self, Self::Error> {
        response::Response::try_from(message).and_then(Self::try_from)
    }
}
