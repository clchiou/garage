//! BEP 5 and BEP 23 Compact Info

use std::iter;
use std::net::{Ipv4Addr, Ipv6Addr, SocketAddrV4, SocketAddrV6};

use bytes::{Buf, BufMut, Bytes, BytesMut};
use snafu::prelude::*;

use crate::node_id::{NODE_ID_SIZE, NodeId};

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Error {
    #[snafu(display("expect size == {expect}: {size}"))]
    Size { size: usize, expect: usize },
    #[snafu(display("expect array size % {unit_size} == 0: {size}"))]
    ArraySize { size: usize, unit_size: usize },
}

pub trait Compact = CompactDecode + CompactEncode;

pub trait CompactSize: Sized {
    const SIZE: usize;

    fn ensure_size(size: usize) -> Result<(), Error> {
        ensure!(
            size == Self::SIZE,
            SizeSnafu {
                size,
                expect: Self::SIZE,
            },
        );
        Ok(())
    }

    fn ensure_array_size(size: usize) -> Result<(), Error> {
        ensure!(
            size % Self::SIZE == 0,
            ArraySizeSnafu {
                size,
                unit_size: Self::SIZE,
            },
        );
        Ok(())
    }
}

pub trait CompactDecode: CompactSize {
    fn decode_unchecked(compact: &[u8]) -> Self;

    fn decode(compact: &[u8]) -> Result<Self, Error> {
        Self::ensure_size(compact.len())?;
        Ok(Self::decode_unchecked(compact))
    }

    fn decode_many(compact: &[u8]) -> Result<impl Iterator<Item = Self>, Error> {
        Self::ensure_array_size(compact.len())?;
        Ok(compact.chunks_exact(Self::SIZE).map(Self::decode_unchecked))
    }
}

pub trait CompactEncode: CompactSize {
    fn encode(&self, buffer: &mut BytesMut);

    fn encode_many<I>(items: I, buffer: &mut BytesMut)
    where
        I: IntoIterator<Item = Self>,
    {
        let items = items.into_iter();
        buffer.reserve(items.size_hint().0 * Self::SIZE);
        for item in items {
            item.encode(buffer);
        }
    }

    fn split(mut buffer: Bytes) -> Result<impl Iterator<Item = Bytes>, Error> {
        Self::ensure_array_size(buffer.len())?;
        Ok(iter::from_fn(move || {
            (!buffer.is_empty()).then(|| buffer.split_to(Self::SIZE))
        }))
    }
}

impl CompactSize for u16 {
    const SIZE: usize = 2;
}

impl CompactDecode for u16 {
    fn decode_unchecked(mut compact: &[u8]) -> Self {
        compact.get_u16()
    }
}

impl CompactEncode for u16 {
    fn encode(&self, buffer: &mut BytesMut) {
        buffer.put_u16(*self);
    }
}

impl CompactSize for Ipv4Addr {
    const SIZE: usize = 4;
}

impl CompactDecode for Ipv4Addr {
    fn decode_unchecked(mut compact: &[u8]) -> Self {
        Self::from_octets(compact.get_u32().to_be_bytes())
    }
}

impl CompactEncode for Ipv4Addr {
    fn encode(&self, buffer: &mut BytesMut) {
        buffer.put_slice(self.as_octets());
    }
}

impl CompactSize for Ipv6Addr {
    const SIZE: usize = 16;
}

impl CompactDecode for Ipv6Addr {
    fn decode_unchecked(mut compact: &[u8]) -> Self {
        Self::from_octets(compact.get_u128().to_be_bytes())
    }
}

impl CompactEncode for Ipv6Addr {
    fn encode(&self, buffer: &mut BytesMut) {
        buffer.put_slice(self.as_octets());
    }
}

impl CompactSize for SocketAddrV4 {
    const SIZE: usize = Ipv4Addr::SIZE + u16::SIZE;
}

impl CompactDecode for SocketAddrV4 {
    fn decode_unchecked(compact: &[u8]) -> Self {
        let (ip, port) = <(Ipv4Addr, u16)>::decode_unchecked(compact);
        Self::new(ip, port)
    }
}

impl CompactEncode for SocketAddrV4 {
    fn encode(&self, buffer: &mut BytesMut) {
        (self.ip(), self.port()).encode(buffer);
    }
}

impl CompactSize for SocketAddrV6 {
    const SIZE: usize = Ipv6Addr::SIZE + u16::SIZE;
}

impl CompactDecode for SocketAddrV6 {
    fn decode_unchecked(compact: &[u8]) -> Self {
        let (ip, port) = <(Ipv6Addr, u16)>::decode_unchecked(compact);
        Self::new(ip, port, 0, 0)
    }
}

impl CompactEncode for SocketAddrV6 {
    fn encode(&self, buffer: &mut BytesMut) {
        (self.ip(), self.port()).encode(buffer);
    }
}

impl CompactSize for NodeId {
    const SIZE: usize = NODE_ID_SIZE;
}

impl CompactDecode for NodeId {
    fn decode_unchecked(compact: &[u8]) -> Self {
        compact.try_into().expect("compact node id")
    }
}

impl CompactEncode for NodeId {
    fn encode(&self, buffer: &mut BytesMut) {
        buffer.put_slice(self.as_ref());
    }
}

// Needed to encode types such as `(&U, &V)` or `Iterator<Item = &T>`.
impl<T> CompactSize for &T
where
    T: CompactSize,
{
    const SIZE: usize = T::SIZE;
}

impl<T> CompactEncode for &T
where
    T: CompactEncode,
{
    fn encode(&self, buffer: &mut BytesMut) {
        (*self).encode(buffer);
    }
}

impl<T0, T1> CompactSize for (T0, T1)
where
    T0: CompactSize,
    T1: CompactSize,
{
    const SIZE: usize = T0::SIZE + T1::SIZE;
}

impl<T0, T1> CompactDecode for (T0, T1)
where
    T0: CompactDecode,
    T1: CompactDecode,
{
    fn decode_unchecked(compact: &[u8]) -> Self {
        let (e0, e1) = compact.split_at(T0::SIZE);
        (T0::decode_unchecked(e0), T1::decode_unchecked(e1))
    }
}

impl<T0, T1> CompactEncode for (T0, T1)
where
    T0: CompactEncode,
    T1: CompactEncode,
{
    fn encode(&self, buffer: &mut BytesMut) {
        self.0.encode(buffer);
        self.1.encode(buffer);
    }
}

impl<T0, T1, T2> CompactSize for (T0, T1, T2)
where
    T0: CompactSize,
    T1: CompactSize,
    T2: CompactSize,
{
    const SIZE: usize = T0::SIZE + T1::SIZE + T2::SIZE;
}

impl<T0, T1, T2> CompactDecode for (T0, T1, T2)
where
    T0: CompactDecode,
    T1: CompactDecode,
    T2: CompactDecode,
{
    fn decode_unchecked(compact: &[u8]) -> Self {
        let (e0, compact) = compact.split_at(T0::SIZE);
        let (e1, e2) = compact.split_at(T1::SIZE);
        (
            T0::decode_unchecked(e0),
            T1::decode_unchecked(e1),
            T2::decode_unchecked(e2),
        )
    }
}

impl<T0, T1, T2> CompactEncode for (T0, T1, T2)
where
    T0: CompactEncode,
    T1: CompactEncode,
    T2: CompactEncode,
{
    fn encode(&self, buffer: &mut BytesMut) {
        self.0.encode(buffer);
        self.1.encode(buffer);
        self.2.encode(buffer);
    }
}

#[cfg(test)]
mod tests {
    use std::fmt;

    use hex_literal::hex;

    use super::*;

    #[test]
    fn compact() {
        fn test<T>(testdata: &[u8], expect: T)
        where
            T: Compact,
            T: Clone + fmt::Debug + PartialEq,
        {
            let mut one_more = testdata.to_vec();
            one_more.push(0x00);
            let mut one_less = testdata.to_vec();
            one_less.pop();

            // decode
            {
                assert_eq!(T::decode(testdata), Ok(expect.clone()));

                assert_eq!(
                    T::decode(&[]),
                    Err(Error::Size {
                        size: 0,
                        expect: testdata.len(),
                    }),
                );
                assert_eq!(
                    T::decode(&one_less),
                    Err(Error::Size {
                        size: one_less.len(),
                        expect: testdata.len(),
                    }),
                );
                assert_eq!(
                    T::decode(&one_more),
                    Err(Error::Size {
                        size: one_more.len(),
                        expect: testdata.len(),
                    }),
                );
            }

            // decode_many
            {
                let mut testdata_many = Vec::new();
                let mut expect_many = Vec::new();
                assert_eq!(
                    T::decode_many(&testdata_many).unwrap().collect::<Vec<_>>(),
                    expect_many,
                );
                for _ in 0..3 {
                    testdata_many.extend_from_slice(testdata);
                    expect_many.push(expect.clone());
                    assert_eq!(
                        T::decode_many(&testdata_many).unwrap().collect::<Vec<_>>(),
                        expect_many,
                    );
                }

                assert_eq!(
                    T::decode_many(&one_less).err().unwrap(),
                    Error::ArraySize {
                        size: one_less.len(),
                        unit_size: testdata.len(),
                    },
                );
                assert_eq!(
                    T::decode_many(&one_more).err().unwrap(),
                    Error::ArraySize {
                        size: one_more.len(),
                        unit_size: testdata.len(),
                    },
                );
            }

            // encode
            {
                let mut buffer = BytesMut::new();
                expect.encode(&mut buffer);
                let mut expect_buffer = testdata.to_vec();
                assert_eq!(buffer, expect_buffer);

                let mut buffer = BytesMut::new();
                (&expect, &expect).encode(&mut buffer);
                expect_buffer.extend_from_slice(testdata);
                assert_eq!(buffer, expect_buffer);

                let mut buffer = BytesMut::new();
                (&expect, &expect, &expect).encode(&mut buffer);
                expect_buffer.extend_from_slice(testdata);
                assert_eq!(buffer, expect_buffer);
            }

            // encode_many and split
            {
                let mut items = Vec::new();
                let mut expect_buffer = Vec::new();
                let mut expect_split = Vec::new();
                {
                    let mut buffer = BytesMut::new();
                    <&T>::encode_many(&items, &mut buffer);
                    assert_eq!(buffer, expect_buffer);
                    assert_eq!(
                        T::split(buffer.freeze()).unwrap().collect::<Vec<_>>(),
                        expect_split,
                    );
                }
                for _ in 0..3 {
                    items.push(expect.clone());
                    expect_buffer.extend_from_slice(testdata);
                    expect_split.push(Bytes::copy_from_slice(testdata));

                    let mut buffer = BytesMut::new();
                    <&T>::encode_many(&items, &mut buffer);
                    assert_eq!(buffer, expect_buffer);
                    assert_eq!(
                        T::split(buffer.freeze()).unwrap().collect::<Vec<_>>(),
                        expect_split,
                    );
                }
            }

            // split error
            {
                assert_eq!(
                    T::split(one_less.clone().into()).err().unwrap(),
                    Error::ArraySize {
                        size: one_less.len(),
                        unit_size: testdata.len(),
                    },
                );
                assert_eq!(
                    T::split(one_more.clone().into()).err().unwrap(),
                    Error::ArraySize {
                        size: one_more.len(),
                        unit_size: testdata.len(),
                    },
                );
            }
        }

        let v4 = Ipv4Addr::new(127, 0, 0, 1);
        let v6 = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
            .parse::<Ipv6Addr>()
            .unwrap();
        let node_id = NodeId::from(hex!("0123456789abcdef 0123456789abcdef deadbeef"));

        test(&hex!("1234"), 0x1234u16);

        test(&hex!("7f 00 00 01"), v4);

        test(&hex!("2001 0db8 85a3 0000 0000 8a2e 0370 7334"), v6);

        test(&hex!("7f 00 00 01 1234"), SocketAddrV4::new(v4, 0x1234));
        test(&hex!("7f 00 00 01 1234"), (v4, 0x1234u16));

        test(
            &hex!("2001 0db8 85a3 0000 0000 8a2e 0370 7334 1234"),
            SocketAddrV6::new(v6, 0x1234, 0, 0),
        );
        test(
            &hex!("2001 0db8 85a3 0000 0000 8a2e 0370 7334 1234"),
            (v6, 0x1234u16),
        );

        test(
            &hex!("0123456789abcdef 0123456789abcdef deadbeef"),
            node_id.clone(),
        );

        test(
            &hex!("0123456789abcdef 0123456789abcdef deadbeef 7f 00 00 01 1234"),
            (node_id.clone(), v4, 0x1234u16),
        );
    }
}
