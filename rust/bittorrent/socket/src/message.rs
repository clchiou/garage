use std::io::Error;
use std::mem;
use std::num::TryFromIntError;

use bytes::{Buf, BufMut, Bytes, BytesMut};
use snafu::prelude::*;

use g1_bytes::BufPeekExt;
use g1_tokio::bstream::StreamRecv;

use bittorrent_base::{BlockDesc, BlockOffset, Features, PieceIndex};

use crate::error;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Message {
    KeepAlive,
    Choke,
    Unchoke,
    Interested,
    NotInterested,
    Have(PieceIndex),
    Bitfield(Bytes),
    Request(BlockDesc),
    Piece(BlockDesc, Bytes),
    Cancel(BlockDesc),

    // BEP 5 DHT Protocol
    Port(u16),

    // BEP 6 Fast Extension
    Suggest(PieceIndex),
    HaveAll,
    HaveNone,
    Reject(BlockDesc),
    AllowedFast(PieceIndex),

    // BEP 10 Extension Protocol
    Extended(u8, Bytes),
}

const ID_CHOKE: u8 = 0;
const ID_UNCHOKE: u8 = 1;
const ID_INTERESTED: u8 = 2;
const ID_NOT_INTERESTED: u8 = 3;
const ID_HAVE: u8 = 4;
const ID_BITFIELD: u8 = 5;
const ID_REQUEST: u8 = 6;
const ID_PIECE: u8 = 7;
const ID_CANCEL: u8 = 8;

const ID_PORT: u8 = 9;

const ID_SUGGEST: u8 = 13;
const ID_HAVE_ALL: u8 = 14;
const ID_HAVE_NONE: u8 = 15;
const ID_REJECT: u8 = 16;
const ID_ALLOWED_FAST: u8 = 17;

const ID_EXTENDED: u8 = 20;

impl Message {
    pub(crate) async fn recv_from<Stream>(stream: &mut Stream) -> Result<Self, Error>
    where
        Stream: StreamRecv<Error = Error> + Send,
    {
        // NOTE: Use peek to ensure cancel safety.
        stream.recv_fill(mem::size_of::<u32>()).await?;
        let size = ensure_limit(stream.buffer().peek_u32().unwrap())?;
        stream.recv_fill(size.try_into().unwrap()).await?;
        Self::decode(stream.buffer())
    }

    fn decode(buffer: &mut BytesMut) -> Result<Self, Error> {
        let size = ensure_limit(buffer.get_u32())?;
        if size == 0 {
            return Ok(Self::KeepAlive);
        }
        let id = buffer.get_u8();
        match id {
            ID_CHOKE => {
                ensure_eq(id, size, 1)?;
                Ok(Self::Choke)
            }
            ID_UNCHOKE => {
                ensure_eq(id, size, 1)?;
                Ok(Self::Unchoke)
            }
            ID_INTERESTED => {
                ensure_eq(id, size, 1)?;
                Ok(Self::Interested)
            }
            ID_NOT_INTERESTED => {
                ensure_eq(id, size, 1)?;
                Ok(Self::NotInterested)
            }
            ID_HAVE => {
                ensure_eq(id, size, 5)?;
                let index = to_usize(buffer.get_u32());
                Ok(Self::Have(index.into()))
            }
            ID_BITFIELD => {
                // TODO: Should we disallow zero bitfield size?
                let size = to_usize(ensure_ge(id, size, 1)?);
                Ok(Self::Bitfield(buffer.split_to(size).freeze()))
            }
            ID_REQUEST => {
                ensure_eq(id, size, 13)?;
                let index = to_usize(buffer.get_u32());
                let offset = u64::from(buffer.get_u32());
                let size = u64::from(buffer.get_u32());
                Ok(Self::Request((index, offset, size).into()))
            }
            ID_PIECE => {
                // TODO: Should we disallow zero piece size?
                let size = u64::from(ensure_ge(id, size, 9)?);
                let index = to_usize(buffer.get_u32());
                let offset = u64::from(buffer.get_u32());
                let payload = buffer.split_to(to_usize(size)).freeze();
                Ok(Self::Piece((index, offset, size).into(), payload))
            }
            ID_CANCEL => {
                ensure_eq(id, size, 13)?;
                let index = to_usize(buffer.get_u32());
                let offset = u64::from(buffer.get_u32());
                let size = u64::from(buffer.get_u32());
                Ok(Self::Cancel((index, offset, size).into()))
            }
            ID_PORT => {
                ensure_eq(id, size, 3)?;
                Ok(Self::Port(buffer.get_u16()))
            }
            ID_SUGGEST => {
                ensure_eq(id, size, 5)?;
                let index = to_usize(buffer.get_u32());
                Ok(Self::Suggest(index.into()))
            }
            ID_HAVE_ALL => {
                ensure_eq(id, size, 1)?;
                Ok(Self::HaveAll)
            }
            ID_HAVE_NONE => {
                ensure_eq(id, size, 1)?;
                Ok(Self::HaveNone)
            }
            ID_REJECT => {
                ensure_eq(id, size, 13)?;
                let index = to_usize(buffer.get_u32());
                let offset = u64::from(buffer.get_u32());
                let size = u64::from(buffer.get_u32());
                Ok(Self::Reject((index, offset, size).into()))
            }
            ID_ALLOWED_FAST => {
                ensure_eq(id, size, 5)?;
                let index = to_usize(buffer.get_u32());
                Ok(Self::AllowedFast(index.into()))
            }
            ID_EXTENDED => {
                // TODO: Should we disallow zero extension payload size?
                let size = to_usize(ensure_ge(id, size, 2)?);
                let id = buffer.get_u8();
                let payload = buffer.split_to(size).freeze();
                Ok(Self::Extended(id, payload))
            }
            _ => Err(error::Error::UnknownId { id }.into()),
        }
    }

    pub(crate) fn encode(&self, buffer: &mut impl BufMut) {
        match self {
            Self::KeepAlive => buffer.put_u32(0),
            Self::Choke => {
                buffer.put_u32(1);
                buffer.put_u8(ID_CHOKE);
            }
            Self::Unchoke => {
                buffer.put_u32(1);
                buffer.put_u8(ID_UNCHOKE);
            }
            Self::Interested => {
                buffer.put_u32(1);
                buffer.put_u8(ID_INTERESTED);
            }
            Self::NotInterested => {
                buffer.put_u32(1);
                buffer.put_u8(ID_NOT_INTERESTED);
            }
            Self::Have(PieceIndex(index)) => {
                buffer.put_u32(5);
                buffer.put_u8(ID_HAVE);
                buffer.put_u32(to_u32(*index));
            }
            Self::Bitfield(payload) => {
                buffer.put_u32(to_u32(1 + payload.len()));
                buffer.put_u8(ID_BITFIELD);
                buffer.put_slice(payload);
            }
            Self::Request(BlockDesc(BlockOffset(PieceIndex(index), offset), size)) => {
                buffer.put_u32(13);
                buffer.put_u8(ID_REQUEST);
                buffer.put_u32(to_u32(*index));
                buffer.put_u32(to_u32(*offset));
                buffer.put_u32(to_u32(*size));
            }
            Self::Piece(BlockDesc(BlockOffset(PieceIndex(index), offset), size), payload) => {
                assert_eq!(to_usize(*size), payload.len());
                buffer.put_u32(to_u32(9 + payload.len()));
                buffer.put_u8(ID_PIECE);
                buffer.put_u32(to_u32(*index));
                buffer.put_u32(to_u32(*offset));
                buffer.put_slice(payload);
            }
            Self::Cancel(BlockDesc(BlockOffset(PieceIndex(index), offset), size)) => {
                buffer.put_u32(13);
                buffer.put_u8(ID_CANCEL);
                buffer.put_u32(to_u32(*index));
                buffer.put_u32(to_u32(*offset));
                buffer.put_u32(to_u32(*size));
            }
            Self::Port(port) => {
                buffer.put_u32(3);
                buffer.put_u8(ID_PORT);
                buffer.put_u16(*port);
            }
            Self::Suggest(PieceIndex(index)) => {
                buffer.put_u32(5);
                buffer.put_u8(ID_SUGGEST);
                buffer.put_u32(to_u32(*index));
            }
            Self::HaveAll => {
                buffer.put_u32(1);
                buffer.put_u8(ID_HAVE_ALL);
            }
            Self::HaveNone => {
                buffer.put_u32(1);
                buffer.put_u8(ID_HAVE_NONE);
            }
            Self::Reject(BlockDesc(BlockOffset(PieceIndex(index), offset), size)) => {
                buffer.put_u32(13);
                buffer.put_u8(ID_REJECT);
                buffer.put_u32(to_u32(*index));
                buffer.put_u32(to_u32(*offset));
                buffer.put_u32(to_u32(*size));
            }
            Self::AllowedFast(PieceIndex(index)) => {
                buffer.put_u32(5);
                buffer.put_u8(ID_ALLOWED_FAST);
                buffer.put_u32(to_u32(*index));
            }
            Self::Extended(id, payload) => {
                buffer.put_u32(to_u32(2 + payload.len()));
                buffer.put_u8(ID_EXTENDED);
                buffer.put_u8(*id);
                buffer.put_slice(payload);
            }
        }
    }

    pub(crate) fn get_feature(&self, features: Features) -> Option<bool> {
        match self {
            Self::Port(_) => Some(features.dht),
            Self::Suggest(_)
            | Self::HaveAll
            | Self::HaveNone
            | Self::Reject(_)
            | Self::AllowedFast(_) => Some(features.fast),
            Self::Extended(..) => Some(features.extension),
            _ => None,
        }
    }
}

fn ensure_limit(size: u32) -> Result<u32, error::Error> {
    let limit = *bittorrent_base::payload_size_limit();
    ensure!(
        size <= limit.try_into().unwrap(),
        error::SizeExceededLimitSnafu { size, limit },
    );
    Ok(size)
}

fn ensure_eq(id: u8, size: u32, expect: u32) -> Result<(), error::Error> {
    ensure!(
        size == expect,
        error::ExpectSizeEqualSnafu { id, size, expect }
    );
    Ok(())
}

fn ensure_ge(id: u8, size: u32, expect: u32) -> Result<u32, error::Error> {
    ensure!(
        size >= expect,
        error::ExpectSizeGreaterOrEqualSnafu { id, size, expect },
    );
    Ok(size - expect)
}

fn to_usize<T>(x: T) -> usize
where
    usize: TryFrom<T, Error = TryFromIntError>,
{
    x.try_into().unwrap()
}

fn to_u32<T>(x: T) -> u32
where
    u32: TryFrom<T, Error = TryFromIntError>,
{
    x.try_into().unwrap()
}

#[cfg(test)]
mod tests {
    use bytes::BytesMut;
    use hex_literal::hex;
    use tokio::io::AsyncWriteExt;

    use g1_tokio::io::RecvStream;

    use super::*;

    #[tokio::test]
    async fn conversion() {
        async fn test_ok(test_data: &[u8], expect: Message) {
            let mut buffer = BytesMut::new();
            buffer.put_slice(test_data);
            assert_eq!(Message::decode(&mut buffer).unwrap(), expect);

            let (mut stream, mut mock) = RecvStream::new_mock(4096);
            mock.write_all(test_data).await.unwrap();
            mock.write_all(b"spam egg").await.unwrap();
            assert_eq!(Message::recv_from(&mut stream).await.unwrap(), expect);
            assert_eq!(stream.buffer().as_ref(), b"spam egg");

            let mut buffer = BytesMut::new();
            expect.encode(&mut buffer);
            assert_eq!(&buffer, test_data);
        }

        async fn test_eq(test_data: &[u8]) {
            if test_data[3] > 1 {
                let mut buffer = BytesMut::new();
                buffer.put_slice(test_data);
                buffer[3] = test_data[3] - 1;
                test_err(
                    &buffer,
                    error::Error::ExpectSizeEqual {
                        id: test_data[4].into(),
                        size: (test_data[3] - 1).into(),
                        expect: test_data[3].into(),
                    },
                )
                .await;
            }

            let mut buffer = BytesMut::new();
            buffer.put_slice(test_data);
            buffer.put_slice(b"spam egg");
            buffer[3] = test_data[3] + 1;
            test_err(
                &buffer,
                error::Error::ExpectSizeEqual {
                    id: test_data[4].into(),
                    size: (test_data[3] + 1).into(),
                    expect: test_data[3].into(),
                },
            )
            .await;
        }

        async fn test_ge(test_data: &[u8]) {
            let mut buffer = BytesMut::new();
            buffer.put_slice(test_data);
            buffer[3] = test_data[3] - 1;
            test_err(
                &buffer,
                error::Error::ExpectSizeGreaterOrEqual {
                    id: test_data[4].into(),
                    size: (test_data[3] - 1).into(),
                    expect: test_data[3].into(),
                },
            )
            .await;
        }

        async fn test_err(test_data: &[u8], expect: error::Error) {
            let (mut stream, mut mock) = RecvStream::new_mock(4096);
            mock.write_all(test_data).await.unwrap();
            assert_eq!(
                Message::recv_from(&mut stream)
                    .await
                    .unwrap_err()
                    .downcast::<error::Error>()
                    .unwrap()
                    .as_ref(),
                &expect,
            );
        }

        test_ok(&hex!("00000000"), Message::KeepAlive).await;

        test_ok(&hex!("00000001 00"), Message::Choke).await;
        test_eq(&hex!("00000001 00")).await;

        test_ok(&hex!("00000001 01"), Message::Unchoke).await;
        test_eq(&hex!("00000001 01")).await;

        test_ok(&hex!("00000001 02"), Message::Interested).await;
        test_eq(&hex!("00000001 02")).await;

        test_ok(&hex!("00000001 03"), Message::NotInterested).await;
        test_eq(&hex!("00000001 03")).await;

        test_ok(&hex!("00000005 04 00000001"), Message::Have(1.into())).await;
        test_eq(&hex!("00000005 04 00000001")).await;

        test_ok(&hex!("00000001 05"), Message::Bitfield(Bytes::new())).await;
        test_ok(
            &hex!("00000002 05 ff"),
            Message::Bitfield(Bytes::from_static(&[0xff])),
        )
        .await;

        test_ok(
            &hex!("0000000d 06 00000001 00000002 00000003"),
            Message::Request((1, 2, 3).into()),
        )
        .await;
        test_eq(&hex!("0000000d 06 00000001 00000002 00000003")).await;

        test_ok(
            &hex!("00000009 07 00000001 00000002"),
            Message::Piece((1, 2, 0).into(), Bytes::new()),
        )
        .await;
        test_ge(&hex!("00000009 07 00000001 00000002")).await;
        test_ok(
            &hex!("0000000a 07 00000001 00000002 ff"),
            Message::Piece((1, 2, 1).into(), Bytes::from_static(&[0xff])),
        )
        .await;

        test_ok(
            &hex!("0000000d 08 00000001 00000002 00000003"),
            Message::Cancel((1, 2, 3).into()),
        )
        .await;
        test_eq(&hex!("0000000d 08 00000001 00000002 00000003")).await;

        test_ok(&hex!("00000003 09 0001"), Message::Port(1)).await;
        test_eq(&hex!("00000003 09 0001")).await;

        test_ok(&hex!("00000005 0d 00000001"), Message::Suggest(1.into())).await;
        test_eq(&hex!("00000005 0d 00000001")).await;

        test_ok(&hex!("00000001 0e"), Message::HaveAll).await;
        test_eq(&hex!("00000001 0e")).await;

        test_ok(&hex!("00000001 0f"), Message::HaveNone).await;
        test_eq(&hex!("00000001 0f")).await;

        test_ok(
            &hex!("0000000d 10 00000001 00000002 00000003"),
            Message::Reject((1, 2, 3).into()),
        )
        .await;
        test_eq(&hex!("0000000d 10 00000001 00000002 00000003")).await;

        test_ok(
            &hex!("00000005 11 00000001"),
            Message::AllowedFast(1.into()),
        )
        .await;
        test_eq(&hex!("00000005 11 00000001")).await;

        test_ok(&hex!("00000002 14 01"), Message::Extended(1, Bytes::new())).await;
        test_ge(&hex!("00000002 14 01")).await;
        test_ok(
            &hex!("00000003 14 01 ff"),
            Message::Extended(1, Bytes::from_static(&[0xff])),
        )
        .await;

        test_err(
            &hex!("00010001"),
            error::Error::SizeExceededLimit {
                size: 65537,
                limit: 65536,
            },
        )
        .await;
        test_err(&hex!("00000001 0a"), error::Error::UnknownId { id: 10 }).await;
    }
}
