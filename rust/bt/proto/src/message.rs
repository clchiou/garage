use std::io;
use std::num::TryFromIntError;

use bytes::{Buf, BufMut, Bytes, BytesMut};
use snafu::prelude::*;

use g1_bytes::BufPeekExt;
use g1_tokio::frame::{Decode, Encode, FrameSink, FrameStream};

use bt_base::{Bitfield, BlockRange, PieceIndex};

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Message {
    KeepAlive,
    Choke,
    Unchoke,
    Interested,
    NotInterested,
    Have(PieceIndex),
    Bitfield(Bytes),
    Request(BlockRange),
    Piece(BlockRange, Bytes),
    Cancel(BlockRange),

    //
    // BEP 5
    //
    Port(u16),

    //
    // BEP 6
    //
    Suggest(PieceIndex),
    HaveAll,
    HaveNone,
    Reject(BlockRange),
    AllowedFast(PieceIndex),

    //
    // BEP 10
    //
    Extended(u8, Bytes),
}

#[derive(Clone, Copy, Debug)]
pub struct Codec;

#[derive(Debug, Snafu)]
pub enum Error {
    #[snafu(display("io error: {source}"))]
    Io { source: io::Error },

    #[snafu(display("expect message {id} size == {expect}: {size}"))]
    Size { id: u8, size: u32, expect: u32 },
    #[snafu(display("expect message {id} size >= {expect}: {size}"))]
    SizeTooSmall { id: u8, size: u32, expect: u32 },
    #[snafu(display("expect message size <= {limit}: {size}"))]
    SizeLimitExceeded { size: u32, limit: u32 },

    #[snafu(display("unknown id: {id}"))]
    UnknownId { id: u8 },
}

// `g1_tokio::frame` requires this.
impl From<io::Error> for Error {
    fn from(source: io::Error) -> Self {
        Self::Io { source }
    }
}

// For convenience.
impl From<Error> for io::Error {
    fn from(error: Error) -> Self {
        match error {
            Error::Io { source } => source,
            _ => Self::other(error),
        }
    }
}

impl Message {
    pub fn bitfield(bitfield: &Bitfield) -> Self {
        Self::Bitfield(Bytes::copy_from_slice(bitfield.as_raw_slice()))
    }
}

impl Codec {
    pub fn stream<I>(input: I) -> FrameStream<I, Self> {
        FrameStream::new(input, Self)
    }

    pub fn sink<O>(output: O) -> FrameSink<O, Self> {
        FrameSink::new(output, Self)
    }
}

const CHOKE: u8 = 0;
const UNCHOKE: u8 = 1;
const INTERESTED: u8 = 2;
const NOT_INTERESTED: u8 = 3;
const HAVE: u8 = 4;
const BITFIELD: u8 = 5;
const REQUEST: u8 = 6;
const PIECE: u8 = 7;
const CANCEL: u8 = 8;

const PORT: u8 = 9;

const SUGGEST: u8 = 13;
const HAVE_ALL: u8 = 14;
const HAVE_NONE: u8 = 15;
const REJECT: u8 = 16;
const ALLOWED_FAST: u8 = 17;

const EXTENDED: u8 = 20;

// TODO: Make this configurable.
const SIZE_LIMIT: u32 = 65536;

impl Decode for Codec {
    type Frame = Message;
    type Error = Error; // Should we use `io::Error` instead?

    fn decode(&mut self, buffer: &mut BytesMut) -> Result<Option<Self::Frame>, Self::Error> {
        macro_rules! ensure_size {
            ($id:ident, $size:ident, $expect:literal $(,)?) => {
                ensure!(
                    $size == $expect,
                    SizeSnafu {
                        id: $id,
                        size: $size,
                        expect: $expect as u32,
                    },
                )
            };
        }

        macro_rules! ensure_size_ge {
            ($id:ident, $size:ident, $expect:literal $(,)?) => {
                ensure!(
                    $size >= $expect,
                    SizeTooSmallSnafu {
                        id: $id,
                        size: $size,
                        expect: $expect as u32,
                    },
                )
            };
        }

        let Ok(size) = buffer.peek_u32() else {
            return Ok(None);
        };
        ensure!(
            size <= SIZE_LIMIT,
            SizeLimitExceededSnafu {
                size,
                limit: SIZE_LIMIT,
            },
        );

        if buffer.len() < 4 + to_usize(size) {
            return Ok(None);
        }

        assert_eq!(buffer.get_u32(), size);

        if size == 0 {
            return Ok(Some(Message::KeepAlive));
        }

        let id = buffer.get_u8();
        Ok(Some(match id {
            CHOKE => {
                ensure_size!(id, size, 1);
                Message::Choke
            }
            UNCHOKE => {
                ensure_size!(id, size, 1);
                Message::Unchoke
            }
            INTERESTED => {
                ensure_size!(id, size, 1);
                Message::Interested
            }
            NOT_INTERESTED => {
                ensure_size!(id, size, 1);
                Message::NotInterested
            }
            HAVE => {
                ensure_size!(id, size, 5);
                Message::Have(PieceIndex(buffer.get_u32()))
            }
            BITFIELD => {
                ensure_size_ge!(id, size, 1);
                Message::Bitfield(buffer.copy_to_bytes(to_usize(size) - 1))
            }
            REQUEST => {
                ensure_size!(id, size, 13);
                Message::Request(BlockRange(
                    PieceIndex(buffer.get_u32()),
                    u64::from(buffer.get_u32()),
                    u64::from(buffer.get_u32()),
                ))
            }
            PIECE => {
                ensure_size_ge!(id, size, 9);
                Message::Piece(
                    BlockRange(
                        PieceIndex(buffer.get_u32()),
                        u64::from(buffer.get_u32()),
                        u64::from(size - 9),
                    ),
                    buffer.copy_to_bytes(to_usize(size) - 9),
                )
            }
            CANCEL => {
                ensure_size!(id, size, 13);
                Message::Cancel(BlockRange(
                    PieceIndex(buffer.get_u32()),
                    u64::from(buffer.get_u32()),
                    u64::from(buffer.get_u32()),
                ))
            }
            PORT => {
                ensure_size!(id, size, 3);
                Message::Port(buffer.get_u16())
            }
            SUGGEST => {
                ensure_size!(id, size, 5);
                Message::Suggest(PieceIndex(buffer.get_u32()))
            }
            HAVE_ALL => {
                ensure_size!(id, size, 1);
                Message::HaveAll
            }
            HAVE_NONE => {
                ensure_size!(id, size, 1);
                Message::HaveNone
            }
            REJECT => {
                ensure_size!(id, size, 13);
                Message::Reject(BlockRange(
                    PieceIndex(buffer.get_u32()),
                    u64::from(buffer.get_u32()),
                    u64::from(buffer.get_u32()),
                ))
            }
            ALLOWED_FAST => {
                ensure_size!(id, size, 5);
                Message::AllowedFast(PieceIndex(buffer.get_u32()))
            }
            EXTENDED => {
                ensure_size_ge!(id, size, 2);
                Message::Extended(buffer.get_u8(), buffer.copy_to_bytes(to_usize(size) - 2))
            }
            _ => return Err(Error::UnknownId { id }),
        }))
    }
}

impl Encode<Message> for Codec {
    // This should be `Infallible`, but it cannot be, since it also serves as `Sink::Error`.
    type Error = io::Error;

    fn encode(&mut self, message: Message, buffer: &mut BytesMut) -> Result<(), Self::Error> {
        match message {
            Message::KeepAlive => {
                buffer.put_u32(0);
            }
            Message::Choke => {
                buffer.put_u32(1);
                buffer.put_u8(CHOKE);
            }
            Message::Unchoke => {
                buffer.put_u32(1);
                buffer.put_u8(UNCHOKE);
            }
            Message::Interested => {
                buffer.put_u32(1);
                buffer.put_u8(INTERESTED);
            }
            Message::NotInterested => {
                buffer.put_u32(1);
                buffer.put_u8(NOT_INTERESTED);
            }
            Message::Have(PieceIndex(index)) => {
                buffer.put_u32(5);
                buffer.put_u8(HAVE);
                buffer.put_u32(index);
            }
            Message::Bitfield(payload) => {
                buffer.put_u32(1 + to_u32(payload.len()));
                buffer.put_u8(BITFIELD);
                buffer.put_slice(&payload);
            }
            Message::Request(BlockRange(PieceIndex(index), offset, size)) => {
                buffer.put_u32(13);
                buffer.put_u8(REQUEST);
                buffer.put_u32(index);
                buffer.put_u32(to_u32(offset));
                buffer.put_u32(to_u32(size));
            }
            Message::Piece(BlockRange(PieceIndex(index), offset, size), payload) => {
                let len = to_u32(payload.len());
                assert_eq!(to_u32(size), len);
                buffer.put_u32(9 + len);
                buffer.put_u8(PIECE);
                buffer.put_u32(index);
                buffer.put_u32(to_u32(offset));
                buffer.put_slice(&payload);
            }
            Message::Cancel(BlockRange(PieceIndex(index), offset, size)) => {
                buffer.put_u32(13);
                buffer.put_u8(CANCEL);
                buffer.put_u32(index);
                buffer.put_u32(to_u32(offset));
                buffer.put_u32(to_u32(size));
            }
            Message::Port(port) => {
                buffer.put_u32(3);
                buffer.put_u8(PORT);
                buffer.put_u16(port);
            }
            Message::Suggest(PieceIndex(index)) => {
                buffer.put_u32(5);
                buffer.put_u8(SUGGEST);
                buffer.put_u32(index);
            }
            Message::HaveAll => {
                buffer.put_u32(1);
                buffer.put_u8(HAVE_ALL);
            }
            Message::HaveNone => {
                buffer.put_u32(1);
                buffer.put_u8(HAVE_NONE);
            }
            Message::Reject(BlockRange(PieceIndex(index), offset, size)) => {
                buffer.put_u32(13);
                buffer.put_u8(REJECT);
                buffer.put_u32(index);
                buffer.put_u32(to_u32(offset));
                buffer.put_u32(to_u32(size));
            }
            Message::AllowedFast(PieceIndex(index)) => {
                buffer.put_u32(5);
                buffer.put_u8(ALLOWED_FAST);
                buffer.put_u32(index);
            }
            Message::Extended(id, payload) => {
                buffer.put_u32(2 + to_u32(payload.len()));
                buffer.put_u8(EXTENDED);
                buffer.put_u8(id);
                buffer.put_slice(&payload);
            }
        }
        Ok(())
    }
}

fn to_u32<T>(x: T) -> u32
where
    u32: TryFrom<T, Error = TryFromIntError>,
{
    x.try_into().expect("to_u32")
}

fn to_usize(x: u32) -> usize {
    x.try_into().expect("to_usize")
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use hex_literal::hex;

    use super::*;

    #[test]
    fn codec() {
        for (message, bytes) in [
            (Message::KeepAlive, &hex!("00000000") as &[u8]),
            (Message::Choke, &hex!("00000001 00")),
            (Message::Unchoke, &hex!("00000001 01")),
            (Message::Interested, &hex!("00000001 02")),
            (Message::NotInterested, &hex!("00000001 03")),
            (
                Message::Have(PieceIndex(0x12345678)),
                &hex!("00000005 04 12345678"),
            ),
            (Message::Bitfield(Bytes::new()), &hex!("00000001 05")),
            (
                Message::Bitfield(Bytes::from_static(&hex!("12"))),
                &hex!("00000002 05 12"),
            ),
            (
                Message::Bitfield(Bytes::from_static(&hex!("1234"))),
                &hex!("00000003 05 1234"),
            ),
            (
                Message::Request(BlockRange(PieceIndex(0x10000002), 0x30000004, 0x50000006)),
                &hex!("0000000d 06 10000002 30000004 50000006"),
            ),
            (
                Message::Piece(
                    BlockRange(PieceIndex(0x10000002), 0x30000004, 0),
                    Bytes::new(),
                ),
                &hex!("00000009 07 10000002 30000004"),
            ),
            (
                Message::Piece(
                    BlockRange(PieceIndex(0x10000002), 0x30000004, 1),
                    Bytes::from_static(&hex!("34")),
                ),
                &hex!("0000000a 07 10000002 30000004 34"),
            ),
            (
                Message::Piece(
                    BlockRange(PieceIndex(0x10000002), 0x30000004, 2),
                    Bytes::from_static(&hex!("3456")),
                ),
                &hex!("0000000b 07 10000002 30000004 3456"),
            ),
            (
                Message::Cancel(BlockRange(PieceIndex(0x10000002), 0x30000004, 0x50000006)),
                &hex!("0000000d 08 10000002 30000004 50000006"),
            ),
            (Message::Port(0x1234), &hex!("00000003 09 1234")),
            (
                Message::Suggest(PieceIndex(0x12345678)),
                &hex!("00000005 0d 12345678"),
            ),
            (Message::HaveAll, &hex!("00000001 0e")),
            (Message::HaveNone, &hex!("00000001 0f")),
            (
                Message::Reject(BlockRange(PieceIndex(0x10000002), 0x30000004, 0x50000006)),
                &hex!("0000000d 10 10000002 30000004 50000006"),
            ),
            (
                Message::AllowedFast(PieceIndex(0x12345678)),
                &hex!("00000005 11 12345678"),
            ),
            (
                Message::Extended(0x12, Bytes::new()),
                &hex!("00000002 14 12"),
            ),
            (
                Message::Extended(0x12, Bytes::from_static(&hex!("34"))),
                &hex!("00000003 14 12 34"),
            ),
            (
                Message::Extended(0x12, Bytes::from_static(&hex!("3456"))),
                &hex!("00000004 14 12 3456"),
            ),
        ] {
            assert_matches!(
                Codec.decode(&mut BytesMut::from(bytes)),
                Ok(Some(msg)) if msg == message,
                "message = {message:?}",
            );
            assert_matches!(
                Codec.decode(&mut BytesMut::from(&bytes[0..bytes.len() - 1])),
                Ok(None),
                "message = {message:?}",
            );

            let mut buffer = BytesMut::new();
            assert_matches!(Codec.encode(message, &mut buffer), Ok(()));
            assert_eq!(buffer, bytes);
        }

        for bytes in [
            &hex!("00000002 00 ff") as &[u8],
            &hex!("00000002 01 ff"),
            &hex!("00000002 02 ff"),
            &hex!("00000002 03 ff"),
            &hex!("00000001 04"),
            &hex!("00000001 06"),
            &hex!("00000001 08"),
            &hex!("00000001 09"),
            &hex!("00000001 0d"),
            &hex!("00000002 0e ff"),
            &hex!("00000002 0f ff"),
            &hex!("00000001 10"),
            &hex!("00000001 11"),
        ] {
            assert_matches!(
                Codec.decode(&mut BytesMut::from(bytes)),
                Err(Error::Size { .. }),
                "bytes = {}",
                bytes.escape_ascii(),
            );
        }

        for bytes in [&hex!("00000001 07") as &[u8], &hex!("00000001 14") as &[u8]] {
            assert_matches!(
                Codec.decode(&mut BytesMut::from(bytes)),
                Err(Error::SizeTooSmall { .. }),
                "bytes = {}",
                bytes.escape_ascii(),
            );
        }

        assert_matches!(
            Codec.decode(&mut BytesMut::from(hex!("00010001").as_slice())),
            Err(Error::SizeLimitExceeded {
                size: 65537,
                limit: 65536,
            }),
        );

        assert_matches!(
            Codec.decode(&mut BytesMut::from(hex!("00000001 ff").as_slice())),
            Err(Error::UnknownId { id: 0xff }),
        );
    }
}
