use std::net::SocketAddr;

pub type PeerEndpoint = SocketAddr;

//
// BEP 23
//
macro_rules! generate {
    ($from_compact:path, $to_compact:path $(,)?) => {
        use bytes::{Bytes, BytesMut};

        use crate::compact::{CompactDecode, CompactEncode, CompactSize, Error};

        use super::PeerEndpoint;

        pub const SIZE: usize = CompactPeerEndpoint::SIZE;

        pub fn decode(compact: &[u8]) -> Result<PeerEndpoint, Error> {
            CompactPeerEndpoint::decode(compact).map($from_compact)
        }

        pub fn decode_many(compact: &[u8]) -> Result<impl Iterator<Item = PeerEndpoint>, Error> {
            Ok(CompactPeerEndpoint::decode_many(compact)?.map($from_compact))
        }

        pub fn encode_many<I>(peers: I, buffer: &mut BytesMut)
        where
            I: IntoIterator<Item = PeerEndpoint>,
        {
            CompactPeerEndpoint::encode_many(peers.into_iter().map($to_compact), buffer)
        }

        pub fn to_buffer(peers: &[PeerEndpoint]) -> BytesMut {
            let mut buffer = BytesMut::with_capacity(peers.len() * SIZE);
            encode_many(peers.into_iter().copied(), &mut buffer);
            buffer
        }

        pub fn to_bytes_iter(peers: &[PeerEndpoint]) -> impl Iterator<Item = Bytes> {
            CompactPeerEndpoint::split(to_buffer(peers).freeze()).expect("split")
        }

        pub fn to_array_iter(peers: &[PeerEndpoint]) -> impl Iterator<Item = [u8; SIZE]> {
            peers.into_iter().map(|peer| {
                let mut array = [0u8; SIZE];
                $to_compact(*peer).encode(array.as_mut_slice());
                array
            })
        }
    };
}

pub mod v4 {
    use std::net::SocketAddrV4;

    type CompactPeerEndpoint = SocketAddrV4;

    fn to_compact(peer: PeerEndpoint) -> CompactPeerEndpoint {
        match peer {
            PeerEndpoint::V4(peer) => peer,
            PeerEndpoint::V6(_) => panic!("expect ipv4: {peer}"),
        }
    }

    generate!(PeerEndpoint::V4, to_compact);
}

pub mod v6 {
    use std::net::SocketAddrV6;

    type CompactPeerEndpoint = SocketAddrV6;

    fn to_compact(peer: PeerEndpoint) -> CompactPeerEndpoint {
        match peer {
            PeerEndpoint::V4(_) => panic!("expect ipv6: {peer}"),
            PeerEndpoint::V6(peer) => peer,
        }
    }

    generate!(PeerEndpoint::V6, to_compact);
}
