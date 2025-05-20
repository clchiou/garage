//! BEP 5 and BEP 23 Compact Info Implementation

use std::net::{Ipv4Addr, Ipv6Addr, SocketAddrV4, SocketAddrV6};

use bytes::{Buf, BufMut, Bytes, BytesMut};
use snafu::prelude::*;

use crate::NODE_ID_SIZE;

pub trait Compact: Sized {
    const SIZE: usize;

    fn decode(compact: &[u8]) -> Result<Self, Error>;

    fn encode(&self, buffer: &mut impl BufMut);

    fn ensure_size(size: usize) -> Result<(), Error> {
        ensure!(
            size == Self::SIZE,
            ExpectSizeSnafu {
                size,
                expect: Self::SIZE,
            },
        );
        Ok(())
    }

    fn ensure_array_size(size: usize) -> Result<usize, Error> {
        ensure!(
            size % Self::SIZE == 0,
            ExpectArraySizeSnafu {
                size,
                unit_size: Self::SIZE,
            },
        );
        Ok(size / Self::SIZE)
    }

    fn decode_many<'a>(
        compact: &'a [u8],
    ) -> Result<impl Iterator<Item = Result<Self, Error>> + use<'a, Self>, Error>
    where
        Self: 'a,
    {
        Self::ensure_array_size(compact.len())?;
        Ok(compact.chunks_exact(Self::SIZE).map(Self::decode))
    }

    fn encode_many(items: impl Iterator<Item = Self>, buffer: &mut BytesMut) {
        buffer.reserve(items.size_hint().0 * Self::SIZE);
        Self::encode_iter(items, buffer);
    }

    // TODO: Could we employ specialization and rename this method to `encode_many`?
    fn encode_iter(items: impl Iterator<Item = Self>, buffer: &mut impl BufMut) {
        for item in items {
            item.encode(buffer);
        }
    }

    fn split_buffer(mut buffer: Bytes) -> Result<impl Iterator<Item = Bytes>, Error> {
        let n = Self::ensure_array_size(buffer.len())?;
        Ok((0..n).map(move |_| {
            assert!(!buffer.is_empty());
            buffer.split_to(Self::SIZE)
        }))
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Error {
    #[snafu(display("expect size == {expect}: {size}"))]
    ExpectSize { size: usize, expect: usize },
    #[snafu(display("expect array size % {unit_size} == 0: {size}"))]
    ExpectArraySize { size: usize, unit_size: usize },
}

impl Compact for u16 {
    const SIZE: usize = 2;

    fn decode(mut compact: &[u8]) -> Result<Self, Error> {
        Self::ensure_size(compact.len())?;
        Ok(compact.get_u16())
    }

    fn encode(&self, buffer: &mut impl BufMut) {
        buffer.put_u16(*self);
    }
}

impl Compact for Ipv4Addr {
    const SIZE: usize = 4;

    fn decode(mut compact: &[u8]) -> Result<Self, Error> {
        Self::ensure_size(compact.len())?;
        Ok(Self::from(compact.get_u32()))
    }

    fn encode(&self, buffer: &mut impl BufMut) {
        buffer.put_slice(&self.octets());
    }
}

impl Compact for Ipv6Addr {
    const SIZE: usize = 16;

    fn decode(mut compact: &[u8]) -> Result<Self, Error> {
        Self::ensure_size(compact.len())?;
        Ok(Self::from(compact.get_u128()))
    }

    fn encode(&self, buffer: &mut impl BufMut) {
        buffer.put_slice(&self.octets());
    }
}

impl Compact for SocketAddrV4 {
    const SIZE: usize = 4 + 2;

    fn decode(mut compact: &[u8]) -> Result<Self, Error> {
        Self::ensure_size(compact.len())?;
        let ip = compact.get_u32().into();
        let port = compact.get_u16();
        Ok(Self::new(ip, port))
    }

    fn encode(&self, buffer: &mut impl BufMut) {
        buffer.put_slice(&self.ip().octets());
        buffer.put_u16(self.port());
    }
}

impl Compact for SocketAddrV6 {
    const SIZE: usize = 16 + 2;

    fn decode(mut compact: &[u8]) -> Result<Self, Error> {
        Self::ensure_size(compact.len())?;
        let ip = compact.get_u128().into();
        let port = compact.get_u16();
        Ok(Self::new(ip, port, 0, 0))
    }

    fn encode(&self, buffer: &mut impl BufMut) {
        buffer.put_slice(&self.ip().octets());
        buffer.put_u16(self.port());
    }
}

impl Compact for [u8; NODE_ID_SIZE] {
    const SIZE: usize = NODE_ID_SIZE;

    fn decode(compact: &[u8]) -> Result<Self, Error> {
        Self::ensure_size(compact.len())?;
        Ok(compact.try_into().unwrap())
    }

    fn encode(&self, buffer: &mut impl BufMut) {
        buffer.put_slice(self);
    }
}

impl<T> Compact for &'_ T
where
    T: Compact,
{
    const SIZE: usize = T::SIZE;

    fn decode(_compact: &[u8]) -> Result<Self, Error> {
        // TODO: Can we make calling this method a compile-time error?
        panic!("cannot decode into reference")
    }

    fn encode(&self, buffer: &mut impl BufMut) {
        (*self).encode(buffer)
    }
}

impl<T0, T1> Compact for (T0, T1)
where
    T0: Compact,
    T1: Compact,
{
    const SIZE: usize = T0::SIZE + T1::SIZE;

    fn decode(compact: &[u8]) -> Result<Self, Error> {
        Self::ensure_size(compact.len())?;
        let (e0, e1) = compact.split_at(T0::SIZE);
        Ok((T0::decode(e0)?, T1::decode(e1)?))
    }

    fn encode(&self, buffer: &mut impl BufMut) {
        let (e0, e1) = self;
        e0.encode(buffer);
        e1.encode(buffer);
    }
}

impl<T0, T1, T2> Compact for (T0, T1, T2)
where
    T0: Compact,
    T1: Compact,
    T2: Compact,
{
    const SIZE: usize = T0::SIZE + T1::SIZE + T2::SIZE;

    fn decode(compact: &[u8]) -> Result<Self, Error> {
        Self::ensure_size(compact.len())?;
        let (e0, compact) = compact.split_at(T0::SIZE);
        let (e1, e2) = compact.split_at(T1::SIZE);
        Ok((T0::decode(e0)?, T1::decode(e1)?, T2::decode(e2)?))
    }

    fn encode(&self, buffer: &mut impl BufMut) {
        let (e0, e1, e2) = self;
        e0.encode(buffer);
        e1.encode(buffer);
        e2.encode(buffer);
    }
}

#[cfg(test)]
mod tests {
    use std::fmt;

    use hex_literal::hex;

    use super::*;

    #[test]
    fn compact() {
        fn test<T>(compact: &[u8], expect: T)
        where
            T: Clone + Compact + fmt::Debug + PartialEq,
        {
            let mut off_by_one = compact.to_vec();
            off_by_one.push(0);

            let mut buffer = BytesMut::new();

            //
            // Compact::decode
            //
            assert_eq!(T::decode(compact), Ok(expect.clone()));
            assert_eq!(
                T::decode(&[]),
                Err(Error::ExpectSize {
                    size: 0,
                    expect: compact.len(),
                }),
            );
            assert_eq!(
                T::decode(&compact[1..]),
                Err(Error::ExpectSize {
                    size: compact.len() - 1,
                    expect: compact.len(),
                }),
            );
            assert_eq!(
                T::decode(&off_by_one),
                Err(Error::ExpectSize {
                    size: compact.len() + 1,
                    expect: compact.len(),
                }),
            );

            //
            // Compact::decode_many
            //
            let mut compact_many = BytesMut::new();
            let mut expect_many: Vec<Result<T, Error>> = Vec::new();
            assert_eq!(
                T::decode_many(&compact_many).unwrap().collect::<Vec<_>>(),
                expect_many,
            );
            for _ in 0..3 {
                compact_many.put_slice(compact);
                expect_many.push(Ok(expect.clone()));
                assert_eq!(
                    T::decode_many(&compact_many).unwrap().collect::<Vec<_>>(),
                    expect_many,
                );
            }
            assert_eq!(
                T::decode_many(&compact[1..]).err().unwrap(),
                Error::ExpectArraySize {
                    size: compact.len() - 1,
                    unit_size: compact.len(),
                },
            );
            assert_eq!(
                T::decode_many(&off_by_one).err().unwrap(),
                Error::ExpectArraySize {
                    size: compact.len() + 1,
                    unit_size: compact.len(),
                },
            );

            //
            // Compact::encode
            //
            buffer.clear();
            expect.encode(&mut buffer);
            assert_eq!(buffer, compact);
            buffer.clear();
            (&expect).encode(&mut buffer);
            assert_eq!(buffer, compact);

            //
            // Compact::encode_many
            //
            let mut many = Vec::new();
            let mut expect_buffer = BytesMut::new();
            buffer.clear();
            T::encode_many(many.iter().cloned(), &mut buffer);
            assert_eq!(buffer, expect_buffer);
            for _ in 0..3 {
                many.push(expect.clone());
                expect_buffer.put_slice(compact);
                buffer.clear();
                T::encode_many(many.iter().cloned(), &mut buffer);
                assert_eq!(buffer, expect_buffer);
            }

            //
            // Compact::split_buffer
            //
            let mut expect_bytes = Vec::new();
            buffer.clear();
            assert_eq!(
                T::split_buffer(buffer.clone().freeze())
                    .unwrap()
                    .collect::<Vec<_>>(),
                expect_bytes,
            );
            for _ in 0..3 {
                buffer.put_slice(compact);
                expect_bytes.push(Bytes::copy_from_slice(compact));
                assert_eq!(
                    T::split_buffer(buffer.clone().freeze())
                        .unwrap()
                        .collect::<Vec<_>>(),
                    expect_bytes,
                );
            }
            assert_eq!(
                T::split_buffer(Bytes::copy_from_slice(&compact[1..]))
                    .err()
                    .unwrap(),
                Error::ExpectArraySize {
                    size: compact.len() - 1,
                    unit_size: compact.len(),
                },
            );
            assert_eq!(
                T::split_buffer(Bytes::copy_from_slice(&off_by_one))
                    .err()
                    .unwrap(),
                Error::ExpectArraySize {
                    size: compact.len() + 1,
                    unit_size: compact.len(),
                },
            );
        }

        test(&hex!("1234"), 0x1234u16);

        test(&hex!("7f 00 00 01"), Ipv4Addr::new(127, 0, 0, 1));

        test::<Ipv6Addr>(
            &hex!("2001 0db8 85a3 0000 0000 8a2e 0370 7334"),
            "2001:0db8:85a3:0000:0000:8a2e:0370:7334".parse().unwrap(),
        );

        test(
            &hex!("7f 00 00 01 1234"),
            SocketAddrV4::new(Ipv4Addr::new(127, 0, 0, 1), 0x1234),
        );
        test(
            &hex!("7f 00 00 01 1234"),
            (Ipv4Addr::new(127, 0, 0, 1), 0x1234u16),
        );

        test(
            &hex!("2001 0db8 85a3 0000 0000 8a2e 0370 7334 1234"),
            SocketAddrV6::new(
                "2001:0db8:85a3:0000:0000:8a2e:0370:7334".parse().unwrap(),
                0x1234,
                0,
                0,
            ),
        );
        test::<(Ipv6Addr, u16)>(
            &hex!("2001 0db8 85a3 0000 0000 8a2e 0370 7334 1234"),
            (
                "2001:0db8:85a3:0000:0000:8a2e:0370:7334".parse().unwrap(),
                0x1234,
            ),
        );

        test(
            &hex!("0123456789 abcdef0123 456789abcd ef01234567"),
            hex!("0123456789 abcdef0123 456789abcd ef01234567"),
        );
        test(
            &hex!("0123456789 abcdef0123 456789abcd ef01234567 7f 00 00 01 1234"),
            (
                hex!("0123456789 abcdef0123 456789abcd ef01234567"),
                Ipv4Addr::new(127, 0, 0, 1),
                0x1234u16,
            ),
        );

        let mut buffer = BytesMut::new();
        let x = 0xdeadu16;
        let y = 0xbeefu16;
        (&x, &y).encode(&mut buffer);
        assert_eq!(buffer, hex!("deadbeef").as_slice());
    }
}
