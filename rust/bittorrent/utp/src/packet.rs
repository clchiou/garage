use bytes::{Buf, BufMut, Bytes};
use snafu::prelude::*;

use g1_bytes::{BufExt, BufMutExt};

use crate::timestamp::{self, Timestamp};

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub(crate) enum Error {
    #[snafu(display("duplicated extension: {extension}"))]
    DuplicatedExtension {
        extension: u8,
    },
    #[snafu(display("expect extension {extension} size == {expect}: {size}"))]
    ExpectExtensionSize {
        extension: u8,
        size: usize,
        expect: usize,
    },
    #[snafu(display("expect version == {VERSION}: {version}"))]
    ExpectVersion {
        version: u8,
    },
    Incomplete,
    #[snafu(display("unknown packet type: {packet_type}"))]
    UnknownPacketType {
        packet_type: u8,
    },
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct Packet {
    pub(crate) header: PacketHeader,
    pub(crate) selective_ack: Option<SelectiveAck>,
    pub(crate) payload: Bytes,
}

#[derive(BufExt, BufMutExt, Clone, Debug, Eq, PartialEq)]
pub(crate) struct PacketHeader {
    pub(crate) type_version: u8,
    pub(crate) extension: u8,
    pub(crate) conn_id: u16,
    pub(crate) send_at: u32,
    pub(crate) send_delay: u32,
    pub(crate) window_size: u32,
    pub(crate) seq: u16,
    pub(crate) ack: u16,
}

impl PacketHeader {
    pub(crate) const SIZE: usize = 20;
}

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
#[repr(u8)]
pub(crate) enum PacketType {
    Data = 0,
    Finish = 1,
    State = 2,
    Reset = 3,
    Synchronize = 4,
}

const PACKET_TYPES: &[PacketType] = &[
    PacketType::Data,
    PacketType::Finish,
    PacketType::State,
    PacketType::Reset,
    PacketType::Synchronize,
];

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct SelectiveAck(pub(crate) Bytes);

const VERSION: u8 = 1;

const EXTENSION_NONE: u8 = 0;
const EXTENSION_SELECTIVE_ACK: u8 = 1;
// Unofficial extension that is also deprecated, likely from an early version of libutp.
const EXTENSION_DEPRECATED: u8 = 2;
// Unofficial extension from libtorrent.
const EXTENSION_CLOSE_REASON: u8 = 3;

impl TryFrom<Bytes> for Packet {
    type Error = Error;

    fn try_from(mut buffer: Bytes) -> Result<Self, Self::Error> {
        fn decode_extension(buffer: &mut Bytes) -> Result<(Bytes, u8), Error> {
            let next_extension = buffer.try_get_u8().map_err(|_| Error::Incomplete)?;
            let size = usize::from(buffer.try_get_u8().map_err(|_| Error::Incomplete)?);
            ensure!(buffer.remaining() >= size, IncompleteSnafu);
            Ok((buffer.split_to(size), next_extension))
        }

        let header = buffer
            .try_get_packet_header()
            .map_err(|_| Error::Incomplete)?;

        header.try_packet_type()?;
        let version = header.version();
        ensure!(version == VERSION, ExpectVersionSnafu { version });

        let mut selective_ack = None;
        let mut extension = header.extension;
        while extension != EXTENSION_NONE {
            let (data, next) = decode_extension(&mut buffer)?;
            let size = data.len();
            match extension {
                EXTENSION_SELECTIVE_ACK => {
                    ensure!(
                        selective_ack.is_none(),
                        DuplicatedExtensionSnafu { extension },
                    );
                    // BEP 29 specifies that the size should be at least 4 and in multiples of 4;
                    // however, [libtorrent] disregards this requirement, and so we do not check the
                    // size here.
                    //
                    // [libtorrent]: https://github.com/arvidn/libtorrent/issues/7068
                    selective_ack = Some(SelectiveAck(data));
                }
                EXTENSION_DEPRECATED => {
                    let expect = 8;
                    ensure!(
                        size == expect,
                        ExpectExtensionSizeSnafu {
                            extension,
                            size,
                            expect,
                        },
                    );
                    if data != [0; 8].as_slice() {
                        tracing::warn!(extension_bits = ?data, "expect all-zero extension bits");
                    }
                }
                EXTENSION_CLOSE_REASON => {
                    let expect = 4;
                    ensure!(
                        size == expect,
                        ExpectExtensionSizeSnafu {
                            extension,
                            size,
                            expect,
                        },
                    );
                    let close_reason = (&data[2..4]).get_u16();
                    tracing::debug!(close_reason);
                }
                _ => {
                    tracing::warn!(extension, ?data, "unknown extension");
                }
            }
            extension = next;
        }

        Ok(Self {
            header,
            selective_ack,
            payload: buffer,
        })
    }
}

impl TryFrom<u8> for PacketType {
    type Error = Error;

    fn try_from(packet_type: u8) -> Result<Self, Self::Error> {
        PACKET_TYPES
            .get(usize::from(packet_type))
            .copied()
            .ok_or(Error::UnknownPacketType { packet_type })
    }
}

impl Packet {
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn new(
        packet_type: PacketType,
        conn_id: u16,
        send_at: Timestamp,
        send_delay: u32,
        window_size: usize,
        seq: u16,
        ack: u16,
        selective_ack: Option<SelectiveAck>,
        payload: Bytes,
    ) -> Self {
        let extension = match selective_ack {
            Some(_) => EXTENSION_SELECTIVE_ACK,
            None => EXTENSION_NONE,
        };
        Self {
            header: PacketHeader {
                type_version: ((packet_type as u8) << 4) | VERSION,
                extension,
                conn_id,
                send_at: timestamp::as_micros_u32(send_at),
                send_delay,
                window_size: window_size.try_into().unwrap(),
                seq,
                ack,
            },
            selective_ack,
            payload,
        }
    }

    pub(crate) fn size(&self) -> usize {
        PacketHeader::SIZE
            + self
                .selective_ack
                .as_ref()
                .map(|SelectiveAck(bitmask)| 2 + bitmask.len())
                .unwrap_or(0)
            + self.payload.len()
    }

    pub(crate) fn encode<Buffer>(&self, buffer: &mut Buffer)
    where
        Buffer: BufMut,
    {
        buffer.put_packet_header(&self.header);
        if let Some(SelectiveAck(bitmask)) = &self.selective_ack {
            buffer.put_u8(EXTENSION_NONE);
            buffer.put_u8(bitmask.len().try_into().unwrap());
            buffer.put_slice(bitmask);
        }
        buffer.put_slice(&self.payload);
    }
}

impl PacketHeader {
    fn try_packet_type(&self) -> Result<PacketType, Error> {
        ((self.type_version & 0xf0) >> 4).try_into()
    }

    fn version(&self) -> u8 {
        self.type_version & 0x0f
    }

    pub(crate) fn packet_type(&self) -> PacketType {
        self.try_packet_type().unwrap()
    }

    pub(crate) fn window_size(&self) -> usize {
        self.window_size.try_into().unwrap()
    }

    pub(crate) fn set_send_at(&mut self, send_at: Timestamp) {
        self.send_at = timestamp::as_micros_u32(send_at);
    }
}

#[cfg(test)]
mod tests {
    use bytes::BytesMut;
    use hex_literal::hex;

    use super::*;

    #[test]
    fn packet_type() {
        for packet_type in PACKET_TYPES.iter().copied() {
            assert_eq!(PacketType::try_from(packet_type as u8), Ok(packet_type));
        }
    }

    #[test]
    fn codec() {
        fn test(packet: Packet, expect: &'static [u8]) {
            let mut buffer = BytesMut::with_capacity(expect.len());
            packet.encode(&mut buffer);
            assert_eq!(&buffer, expect);
            assert_eq!(packet.size(), expect.len());
            assert_eq!(
                Packet::try_from(Bytes::from_static(expect)),
                Ok(packet.try_into().unwrap()),
            );
        }

        let mut packet = Packet::new(
            PacketType::Data,
            1,
            Timestamp::from_micros(2),
            3,
            4,
            5,
            6,
            None,
            Bytes::from_static(&[]),
        );
        test(
            packet.clone(),
            &hex!("01 00 0001 00000002 00000003 00000004 0005 0006"),
        );
        packet.header.extension = 1;
        packet.selective_ack = Some(SelectiveAck(Bytes::from_static(&hex!("aabbcc"))));
        test(
            packet,
            &hex!("01 01 0001 00000002 00000003 00000004 0005 0006 00 03 aabbcc"),
        );

        let packet = Packet::new(
            PacketType::Synchronize,
            0x1234,
            Timestamp::from_micros(0x01020304),
            0x05060708,
            0x090a0b0c,
            0x5678,
            0x9abc,
            Some(SelectiveAck(Bytes::from_static(&hex!("01020304")))),
            Bytes::from_static(&hex!("deadbeef")),
        );
        test(
            packet.clone(),
            &hex!(
                "41 01 1234 01020304 05060708 090a0b0c 5678 9abc"
                "00 04 01020304"
                "deadbeef"
            ),
        );
        let bytes = Bytes::from_static(&hex!(
            "41 01 1234 01020304 05060708 090a0b0c 5678 9abc"
            "02 04 01020304"
            "03 08 00000000 00000000"
            "00 04 00000000"
            "deadbeef"
        ));
        assert_eq!(Packet::try_from(bytes), Ok(packet));
    }

    #[test]
    fn decode_error() {
        fn test_incomplete(buffer: &'static [u8]) {
            for n in 1..buffer.len() {
                test(&buffer[..n], Error::Incomplete);
            }
        }

        fn test(buffer: &'static [u8], expect: Error) {
            assert_eq!(Packet::try_from(Bytes::from_static(buffer)), Err(expect));
        }

        test_incomplete(&hex!("01 00 0001 00000002 00000003 00000004 0005 0006"));
        test_incomplete(&hex!(
            "01 01 0001 00000002 00000003 00000004 0005 0006 00 04 01020304"
        ));

        test(
            &hex!("51 00 0001 00000002 00000003 00000004 0005 0006"),
            Error::UnknownPacketType { packet_type: 5 },
        );

        test(
            &hex!("02 00 0001 00000002 00000003 00000004 0005 0006"),
            Error::ExpectVersion { version: 2 },
        );

        test(
            &hex!("01 02 0001 00000002 00000003 00000004 0005 0006 00 01 ff"),
            Error::ExpectExtensionSize {
                extension: 2,
                size: 1,
                expect: 8,
            },
        );
        test(
            &hex!("01 03 0001 00000002 00000003 00000004 0005 0006 00 01 ff"),
            Error::ExpectExtensionSize {
                extension: 3,
                size: 1,
                expect: 4,
            },
        );

        test(
            &hex!("01 01 0001 00000002 00000003 00000004 0005 0006 01 04 01020304 00 00"),
            Error::DuplicatedExtension { extension: 1 },
        );
    }
}
