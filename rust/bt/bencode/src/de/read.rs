use std::io::{self, ErrorKind};
use std::ptr;

use bytes::{Buf, BufMut, Bytes, BytesMut};
use serde::de::{self, Unexpected};
use snafu::prelude::*;

use crate::bstr::DeserializableBStr;
use crate::error::io::Error as IoError;
use crate::error::{
    self, ByteStringSizeExceededSnafu, Error, IncompleteSnafu, IntegerBufferOverflowSnafu,
};
use crate::int::{INTEGER_BUF_SIZE, Int};
use crate::mut_ref::MutRef;

use super::strict::Strictness;

pub(crate) trait Read<'de, E>
where
    E: de::Error,
{
    type Bytes: DeserializableBStr<'de>;

    type Tee<'t>: Read<'de, E> + Tee<'de>
    where
        Self: 't;

    fn read_u8(&mut self) -> Result<u8, E>;

    /// Reads up to the delimiter, which is not included in `buf`.
    fn read_until(&mut self, delimiter: u8, buf: &mut [u8], offset: usize) -> Result<usize, E>;

    fn read_bytes(&mut self, size: usize) -> Result<Self::Bytes, E>;

    fn tee(&mut self) -> Self::Tee<'_>;
}

pub(crate) trait Tee<'de> {
    type Bytes: DeserializableBStr<'de>;

    // TODO: This feels awkward, but we need it because `Deserializer` peeks at the input before it
    // is instructed to "tee" the input.  Therefore, `Deserializer` needs to be able to "unread"
    // one byte of input data.
    fn unread_u8(&mut self, b: u8);

    fn into_bytes(self) -> Self::Bytes;
}

impl<'de, R, E> Read<'de, E> for MutRef<'_, R>
where
    R: Read<'de, E>,
    E: de::Error,
{
    type Bytes = R::Bytes;

    type Tee<'t>
        = R::Tee<'t>
    where
        Self: 't;

    fn read_u8(&mut self) -> Result<u8, E> {
        self.0.read_u8()
    }

    fn read_until(&mut self, delimiter: u8, buf: &mut [u8], offset: usize) -> Result<usize, E> {
        self.0.read_until(delimiter, buf, offset)
    }

    fn read_bytes(&mut self, size: usize) -> Result<Self::Bytes, E> {
        self.0.read_bytes(size)
    }

    fn tee(&mut self) -> Self::Tee<'_> {
        self.0.tee()
    }
}

impl<'de, R> Read<'de, Error> for R
where
    R: Buf,
{
    type Bytes = Vec<u8>;

    type Tee<'t>
        = OwnedTee<&'t mut Self>
    where
        Self: 't;

    fn read_u8(&mut self) -> Result<u8, Error> {
        self.try_get_u8().map_err(|_| Error::Incomplete)
    }

    fn read_until(&mut self, delimiter: u8, buf: &mut [u8], offset: usize) -> Result<usize, Error> {
        for (n, ptr) in buf[offset..].iter_mut().enumerate() {
            *ptr = self.read_u8()?;
            if ptr == &delimiter {
                return Ok(offset + n);
            }
        }
        ensure!(
            self.read_u8()? == delimiter,
            IntegerBufferOverflowSnafu {
                buffer: Bytes::copy_from_slice(buf),
            },
        );
        Ok(buf.len())
    }

    fn read_bytes(&mut self, size: usize) -> Result<Self::Bytes, Error> {
        // It is important to do the check before actually allocating the buffer.
        ensure!(size <= self.remaining(), IncompleteSnafu);
        let mut buf = vec![0; size];
        self.try_copy_to_slice(buf.as_mut_slice())
            .map_err(|_| Error::Incomplete)?;
        Ok(buf)
    }

    fn tee(&mut self) -> Self::Tee<'_> {
        OwnedTee::new(self)
    }
}

// TODO: What limit value should we use?
const BYTE_STRING_SIZE_LIMIT: usize = 64 * 1024 * 1024; // 64 MB

impl<'de, R> Read<'de, IoError> for R
where
    R: io::Read,
{
    type Bytes = Vec<u8>;

    type Tee<'t>
        = OwnedTee<&'t mut Self>
    where
        Self: 't;

    fn read_u8(&mut self) -> Result<u8, IoError> {
        let mut buf = [0u8];
        self.read_exact(&mut buf).map_err(to_io_error)?;
        Ok(buf[0])
    }

    fn read_until(
        &mut self,
        delimiter: u8,
        buf: &mut [u8],
        offset: usize,
    ) -> Result<usize, IoError> {
        for (n, ptr) in buf[offset..].iter_mut().enumerate() {
            *ptr = self.read_u8()?;
            if ptr == &delimiter {
                return Ok(offset + n);
            }
        }
        ensure!(
            self.read_u8()? == delimiter,
            IntegerBufferOverflowSnafu {
                buffer: Bytes::copy_from_slice(buf),
            },
        );
        Ok(buf.len())
    }

    fn read_bytes(&mut self, size: usize) -> Result<Self::Bytes, IoError> {
        ensure!(
            size <= BYTE_STRING_SIZE_LIMIT,
            ByteStringSizeExceededSnafu { size },
        );
        let mut buf = vec![0; size];
        self.read_exact(buf.as_mut_slice()).map_err(to_io_error)?;
        Ok(buf)
    }

    fn tee(&mut self) -> Self::Tee<'_> {
        OwnedTee::new(self)
    }
}

fn to_io_error(source: io::Error) -> IoError {
    if source.kind() == ErrorKind::UnexpectedEof {
        IoError::Bencode {
            source: Error::Incomplete,
        }
    } else {
        IoError::Io { source }
    }
}

pub(crate) struct OwnedTee<R>(R, BytesMut);

impl<R> OwnedTee<R> {
    pub(super) fn new(reader: R) -> Self {
        Self(reader, BytesMut::new())
    }
}

impl<'de, R, E> Read<'de, E> for OwnedTee<R>
where
    R: Read<'de, E>,
    E: de::Error,
{
    type Bytes = R::Bytes;

    type Tee<'t>
        = OwnedTee<MutRef<'t, Self>>
    where
        Self: 't;

    fn read_u8(&mut self) -> Result<u8, E> {
        let b = self.0.read_u8()?;
        self.1.put_u8(b);
        Ok(b)
    }

    fn read_until(&mut self, delimiter: u8, buf: &mut [u8], offset: usize) -> Result<usize, E> {
        let end = self.0.read_until(delimiter, buf, offset)?;
        self.1.put_slice(&buf[offset..end]);
        self.1.put_u8(delimiter);
        Ok(end)
    }

    fn read_bytes(&mut self, size: usize) -> Result<Self::Bytes, E> {
        let bytes = self.0.read_bytes(size)?;
        self.1.put_slice(bytes.as_ref());
        Ok(bytes)
    }

    fn tee(&mut self) -> Self::Tee<'_> {
        OwnedTee::new(MutRef(self))
    }
}

impl<'de, R> Tee<'de> for OwnedTee<R> {
    type Bytes = Vec<u8>;

    fn unread_u8(&mut self, b: u8) {
        assert!(self.1.is_empty());
        self.1.put_u8(b);
    }

    fn into_bytes(self) -> Self::Bytes {
        self.1.into()
    }
}

// To work around this conflict:
// ```
// impl<B: Buf>  Read<Error> for B                 { ... }
// impl<'s, 'de> Read<Error> for &'s mut &'de [u8] { ... }
// ```
pub(super) struct SliceReader<'s, 'de>(&'s mut &'de [u8]);

impl<'s, 'de> SliceReader<'s, 'de> {
    pub(super) fn new(slice: &'s mut &'de [u8]) -> Self {
        Self(slice)
    }
}

impl<'s, 'de> Read<'de, Error> for SliceReader<'s, 'de> {
    type Bytes = &'de [u8];

    type Tee<'t>
        = BorrowedTee<'t, 'de>
    where
        Self: 't;

    fn read_u8(&mut self) -> Result<u8, Error> {
        Ok(*self.0.split_off_first().ok_or(Error::Incomplete)?)
    }

    fn read_until(&mut self, delimiter: u8, buf: &mut [u8], offset: usize) -> Result<usize, Error> {
        let remaining = buf.len() - offset;
        let n = self
            .0
            .iter()
            .take(remaining + 1)
            .position(|&b| b == delimiter)
            .ok_or_else(|| {
                if self.0.len() > remaining {
                    buf[offset..].copy_from_slice(&self.0[..remaining]);
                    Error::IntegerBufferOverflow {
                        buffer: Bytes::copy_from_slice(buf),
                    }
                } else {
                    Error::Incomplete
                }
            })?;
        let end = offset + n;
        buf[offset..end].copy_from_slice(self.0.split_off(..n).expect("buf"));
        self.0.split_off_first();
        Ok(end)
    }

    fn read_bytes(&mut self, size: usize) -> Result<Self::Bytes, Error> {
        self.0.split_off(..size).ok_or(Error::Incomplete)
    }

    fn tee(&mut self) -> Self::Tee<'_> {
        BorrowedTee::new(&mut *self.0)
    }
}

pub(super) struct BorrowedTee<'s, 'de>(SliceReader<'s, 'de>, &'de [u8]);

impl<'s, 'de> BorrowedTee<'s, 'de> {
    pub(super) fn new(slice: &'s mut &'de [u8]) -> Self {
        let origin = &**slice;
        Self(SliceReader::new(slice), origin)
    }
}

impl<'s, 'de> Read<'de, Error> for BorrowedTee<'s, 'de> {
    type Bytes = &'de [u8];

    type Tee<'t>
        = BorrowedTee<'t, 'de>
    where
        Self: 't;

    fn read_u8(&mut self) -> Result<u8, Error> {
        self.0.read_u8()
    }

    fn read_until(&mut self, delimiter: u8, buf: &mut [u8], offset: usize) -> Result<usize, Error> {
        self.0.read_until(delimiter, buf, offset)
    }

    fn read_bytes(&mut self, size: usize) -> Result<Self::Bytes, Error> {
        self.0.read_bytes(size)
    }

    fn tee(&mut self) -> Self::Tee<'_> {
        self.0.tee()
    }
}

impl<'s, 'de> Tee<'de> for BorrowedTee<'s, 'de> {
    type Bytes = &'de [u8];

    fn unread_u8(&mut self, b: u8) {
        assert!(ptr::eq(*self.0.0, self.1));
        let slice = ptr::slice_from_raw_parts(self.1.as_ptr().wrapping_sub(1), self.1.len() + 1);
        self.1 = unsafe { &*slice };
        assert_eq!(self.1[0], b);
    }

    fn into_bytes(self) -> Self::Bytes {
        let n = unsafe { (*self.0.0).as_ptr().offset_from_unsigned(self.1.as_ptr()) };
        &self.1[..n]
    }
}

//
// Bencode helpers.
//

// It seems like a good idea to split the helper functions into a separate trait so that `Read`
// does not take `S` as a generic parameter.
pub(crate) trait ReadExt<'de, S, E>: Read<'de, E>
where
    S: Strictness,
    E: error::de::Error,
{
    fn read_first_token(&mut self) -> Result<Token, E> {
        match self.read_u8() {
            Ok(b) => Ok(Token::new(b)?),
            Err(error) => Err(if error.is_incomplete() {
                Error::Eof.into()
            } else {
                error
            }),
        }
    }

    fn read_token(&mut self) -> Result<Token, E> {
        Ok(Token::new(self.read_u8()?)?)
    }

    fn read_item_token(&mut self) -> Result<Option<Token>, E> {
        Ok(match self.read_u8()? {
            b'e' => None,
            prefix => Some(Token::new(prefix)?),
        })
    }

    fn read_byte_string(&mut self, b0: u8) -> Result<Self::Bytes, E> {
        let mut buf = [0u8; INTEGER_BUF_SIZE];
        buf[0] = b0;
        let end = self.read_until(b':', &mut buf, 1)?;
        self.read_bytes(S::parse_integer(&buf[..end])?)
    }

    fn read_integer<I>(&mut self) -> Result<I, E>
    where
        I: Int,
    {
        let mut buf = [0u8; INTEGER_BUF_SIZE];
        let end = self.read_until(b'e', &mut buf, 0)?;
        Ok(S::parse_integer(&buf[..end])?)
    }
}

impl<'de, R, S, E> ReadExt<'de, S, E> for R
where
    R: Read<'de, E>,
    S: Strictness,
    E: error::de::Error,
{
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) enum Token {
    ByteString(u8),
    Integer,
    List,
    Dictionary,
}

impl Token {
    fn new(prefix: u8) -> Result<Self, Error> {
        match prefix {
            b'0'..=b'9' => Ok(Self::ByteString(prefix)),
            b'i' => Ok(Self::Integer),
            b'l' => Ok(Self::List),
            b'd' => Ok(Self::Dictionary),
            _ => Err(Error::Prefix { prefix }),
        }
    }

    pub(super) fn to_type_name(&self) -> &'static str {
        match self {
            Self::ByteString(_) => "byte string",
            Self::Integer => "integer",
            Self::List => "list",
            Self::Dictionary => "dictionary",
        }
    }

    pub(super) fn to_unexpected(&self) -> Unexpected {
        match self {
            Self::ByteString(_) => Unexpected::Other("byte string"),
            Self::Integer => Unexpected::Other("integer"),
            Self::List => Unexpected::Seq,
            Self::Dictionary => Unexpected::Map,
        }
    }

    pub(super) fn to_prefix(&self) -> u8 {
        match self {
            Self::ByteString(prefix) => *prefix,
            Self::Integer => b'i',
            Self::List => b'l',
            Self::Dictionary => b'd',
        }
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use super::super::strict::Strict;

    use super::*;

    fn read_ext(testdata: &[u8]) -> impl ReadExt<'static, Strict, Error, Bytes = Vec<u8>> {
        Bytes::copy_from_slice(testdata)
    }

    #[test]
    fn read_u8() {
        let mut testdata = b"0".as_slice();

        let mut reader = Bytes::from_static(testdata);
        assert_eq!(reader.read_u8(), Ok(b'0'));
        assert_eq!(reader.read_u8(), Err(Error::Incomplete));

        let mut reader = Bytes::from_static(testdata).reader();
        assert_matches!(reader.read_u8(), Ok(b'0'));
        assert_matches!(
            reader.read_u8(),
            Err(IoError::Bencode {
                source: Error::Incomplete,
            }),
        );

        let mut reader = SliceReader::new(&mut testdata);
        assert_eq!(reader.read_u8(), Ok(b'0'));
        assert_eq!(reader.read_u8(), Err(Error::Incomplete));
    }

    #[test]
    fn read_until() {
        fn test_ok(delimiter: u8, expect_n: usize, expect_data: &[u8]) {
            let mut testdata = b"0123456789".as_slice();
            let mut buf = [0u8; 4];

            let mut reader = Bytes::from_static(testdata);
            assert_eq!(reader.read_until(delimiter, &mut buf, 0), Ok(expect_n));
            assert_eq!(&buf[0..expect_n], expect_data);
            assert_eq!(reader.read_u8().unwrap(), delimiter + 1);

            let mut reader = Bytes::from_static(testdata).reader();
            assert_matches!(reader.read_until(delimiter, &mut buf, 0), Ok(n) if n == expect_n);
            assert_eq!(&buf[0..expect_n], expect_data);
            assert_eq!(reader.read_u8().unwrap(), delimiter + 1);

            let mut reader = SliceReader::new(&mut testdata);
            assert_eq!(reader.read_until(delimiter, &mut buf, 0), Ok(expect_n));
            assert_eq!(&buf[0..expect_n], expect_data);
            assert_eq!(reader.read_u8().unwrap(), delimiter + 1);
        }

        test_ok(b'0', 0, b"");
        test_ok(b'1', 1, b"0");
        test_ok(b'2', 2, b"01");
        test_ok(b'3', 3, b"012");
        test_ok(b'4', 4, b"0123");

        fn test_err_overflow(mut testdata: &'static [u8]) {
            let mut buf = [0u8; 4];
            let expect = Bytes::from_static(&testdata[..buf.len()]);

            let mut reader = Bytes::from_static(testdata);
            assert_eq!(
                reader.read_until(b'5', &mut buf, 0),
                Err(Error::IntegerBufferOverflow {
                    buffer: expect.clone(),
                }),
            );

            let mut reader = Bytes::from_static(testdata).reader();
            assert_matches!(
                reader.read_until(b'5', &mut buf, 0),
                Err(IoError::Bencode { source: Error::IntegerBufferOverflow { buffer } })
                if buffer == expect,
            );

            let mut reader = SliceReader::new(&mut testdata);
            assert_eq!(
                reader.read_until(b'5', &mut buf, 0),
                Err(Error::IntegerBufferOverflow { buffer: expect }),
            );
        }

        test_err_overflow(b"01234");
        test_err_overflow(b"012345");

        fn test_err_incomplete(mut testdata: &'static [u8]) {
            let mut buf = [0u8; 4];

            let mut reader = Bytes::from_static(testdata);
            assert_eq!(reader.read_until(b'5', &mut buf, 0), Err(Error::Incomplete));

            let mut reader = Bytes::from_static(testdata).reader();
            assert_matches!(
                reader.read_until(b'5', &mut buf, 0),
                Err(IoError::Bencode {
                    source: Error::Incomplete,
                }),
            );

            let mut reader = SliceReader::new(&mut testdata);
            assert_eq!(reader.read_until(b'5', &mut buf, 0), Err(Error::Incomplete));
        }

        test_err_incomplete(b"");
        test_err_incomplete(b"0");
        test_err_incomplete(b"01");
        test_err_incomplete(b"012");
        test_err_incomplete(b"0123");

        {
            for offset in 0..5 {
                let testdata = b"0123456789".as_slice();
                let mut reader = Bytes::from_static(testdata);
                let mut buf = [0u8; 5];
                buf[..offset].copy_from_slice(&reader.read_bytes(offset).unwrap());
                assert_eq!(reader.read_until(b'5', &mut buf, offset), Ok(5));
                assert_eq!(&buf, b"01234");
                assert_eq!(reader.read_u8(), Ok(b'6'));
            }

            for offset in 0..5 {
                let testdata = b"0123456789".as_slice();
                let mut reader = Bytes::from_static(testdata);
                let mut buf = [0u8; 5];
                buf[..offset].copy_from_slice(&reader.read_bytes(offset).unwrap());
                assert_eq!(
                    reader.read_until(b'6', &mut buf, offset),
                    Err(Error::IntegerBufferOverflow {
                        buffer: Bytes::from_static(b"01234")
                    }),
                );
            }

            for offset in 0..5 {
                let testdata = b"01234".as_slice();
                let mut reader = Bytes::from_static(testdata);
                let mut buf = [0u8; 5];
                buf[..offset].copy_from_slice(&reader.read_bytes(offset).unwrap());
                assert_eq!(
                    reader.read_until(b'5', &mut buf, offset),
                    Err(Error::Incomplete),
                );
            }
        }

        {
            for offset in 0..5 {
                let mut testdata = b"0123456789".as_slice();
                let mut reader = SliceReader::new(&mut testdata);
                let mut buf = [0u8; 5];
                buf[..offset].copy_from_slice(reader.read_bytes(offset).unwrap());
                assert_eq!(reader.read_until(b'5', &mut buf, offset), Ok(5));
                assert_eq!(&buf, b"01234");
                assert_eq!(reader.read_u8(), Ok(b'6'));
            }

            for offset in 0..5 {
                let mut testdata = b"0123456789".as_slice();
                let mut reader = SliceReader::new(&mut testdata);
                let mut buf = [0u8; 5];
                buf[..offset].copy_from_slice(reader.read_bytes(offset).unwrap());
                assert_eq!(
                    reader.read_until(b'6', &mut buf, offset),
                    Err(Error::IntegerBufferOverflow {
                        buffer: Bytes::from_static(b"01234")
                    }),
                );
            }

            for offset in 0..5 {
                let mut testdata = b"01234".as_slice();
                let mut reader = SliceReader::new(&mut testdata);
                let mut buf = [0u8; 5];
                buf[..offset].copy_from_slice(reader.read_bytes(offset).unwrap());
                assert_eq!(
                    reader.read_until(b'5', &mut buf, offset),
                    Err(Error::Incomplete),
                );
            }
        }
    }

    #[test]
    fn read_bytes() {
        fn test_ok(n: usize, expect: &[u8]) {
            let mut testdata = b"0123456789".as_slice();

            let mut reader = Bytes::from_static(testdata);
            assert_eq!(reader.read_bytes(n), Ok(expect.to_vec()));

            let mut reader = Bytes::from_static(testdata).reader();
            assert_matches!(reader.read_bytes(n), Ok(x) if x == expect);

            let mut reader = SliceReader::new(&mut testdata);
            assert_eq!(reader.read_bytes(n), Ok(expect));
        }

        test_ok(0, b"");
        test_ok(1, b"0");
        test_ok(2, b"01");
        test_ok(3, b"012");
        test_ok(10, b"0123456789");

        {
            let mut testdata = b"0123456789".as_slice();
            let n_plus_1 = testdata.len() + 1;

            let mut reader = Bytes::from_static(testdata);
            assert_eq!(reader.read_bytes(n_plus_1), Err(Error::Incomplete));

            let mut reader = Bytes::from_static(testdata).reader();
            assert_matches!(
                reader.read_bytes(n_plus_1),
                Err(IoError::Bencode {
                    source: Error::Incomplete,
                }),
            );

            let mut reader = SliceReader::new(&mut testdata);
            assert_eq!(reader.read_bytes(n_plus_1), Err(Error::Incomplete));
        }

        let mut reader = Bytes::from_static(b"").reader();
        assert_matches!(
            reader.read_bytes(BYTE_STRING_SIZE_LIMIT + 1),
            Err(IoError::Bencode {
                source: Error::ByteStringSizeExceeded { .. },
            }),
        );
    }

    #[test]
    fn read_bytes_never_capacity_overflow() {
        let mut reader = Bytes::from_static(b"");
        assert_eq!(reader.read_bytes(usize::MAX), Err(Error::Incomplete));

        let mut reader = Bytes::from_static(b"").reader();
        assert_matches!(
            reader.read_bytes(usize::MAX),
            Err(IoError::Bencode {
                source: Error::ByteStringSizeExceeded { .. },
            }),
        );

        let mut reader = b"".as_slice();
        let mut reader = SliceReader::new(&mut reader);
        assert_eq!(reader.read_bytes(usize::MAX), Err(Error::Incomplete));
    }

    #[test]
    fn tee() {
        //
        // `OwnedTee`
        //

        let mut reader = Bytes::from_static(b"0123456789");
        let mut tee = reader.tee();
        assert_eq!(tee.read_u8(), Ok(b'0'));
        assert_eq!(&*tee.into_bytes(), b"0");

        let mut reader = Bytes::from_static(b"0123456789");
        let mut tee = reader.tee();
        assert_eq!(tee.read_until(b'3', &mut [0u8; 3], 0), Ok(3));
        assert_eq!(&*tee.into_bytes(), b"0123");

        let mut reader = Bytes::from_static(b"0123456789");
        let mut tee = reader.tee();
        assert_eq!(tee.read_bytes(4), Ok(b"0123".into()));
        assert_eq!(&*tee.into_bytes(), b"0123");

        let mut reader = Bytes::from_static(b"0123456789");
        let mut tee = reader.tee();
        let mut buf = [0u8; 3];
        buf[0] = tee.read_u8().unwrap();
        assert_eq!(tee.read_until(b'3', &mut buf, 1), Ok(3));
        assert_eq!(&buf[..3], b"012");
        assert_eq!(&*tee.into_bytes(), b"0123");

        //
        // `BorrowedTee`
        //

        let mut reader = b"0123456789".as_slice();
        let mut reader = SliceReader::new(&mut reader);
        let mut tee = reader.tee();
        assert_eq!(tee.read_u8(), Ok(b'0'));
        assert_eq!(tee.into_bytes(), b"0");

        let mut reader = b"0123456789".as_slice();
        let mut reader = SliceReader::new(&mut reader);
        let mut tee = reader.tee();
        assert_eq!(tee.read_until(b'3', &mut [0u8; 3], 0), Ok(3));
        assert_eq!(tee.into_bytes(), b"0123");

        let mut reader = b"0123456789".as_slice();
        let mut reader = SliceReader::new(&mut reader);
        let mut tee = reader.tee();
        assert_eq!(tee.read_bytes(4), Ok(b"0123".as_slice()));
        assert_eq!(tee.into_bytes(), b"0123");

        let mut reader = b"0123456789".as_slice();
        let mut reader = SliceReader::new(&mut reader);
        let mut tee = reader.tee();
        let mut buf = [0u8; 3];
        buf[0] = tee.read_u8().unwrap();
        assert_eq!(tee.read_until(b'3', &mut buf, 1), Ok(3));
        assert_eq!(&buf[..3], b"012");
        assert_eq!(&*tee.into_bytes(), b"0123");
    }

    #[test]
    fn tee_unread_u8() {
        //
        // `OwnedTee`
        //

        let mut reader = Bytes::from_static(b"0123");
        assert_eq!(reader.read_u8(), Ok(b'0'));

        let mut tee = reader.tee();
        assert_eq!(&*tee.1, b"");

        tee.unread_u8(b'0');
        assert_eq!(&*tee.1, b"0");

        assert_eq!(tee.into_bytes(), b"0");

        //
        // `BorrowedTee`
        //

        let mut reader = b"0123".as_slice();
        let mut reader = SliceReader::new(&mut reader);
        assert_eq!(reader.read_u8(), Ok(b'0'));

        let mut tee = reader.tee();
        assert_eq!(*tee.0.0, b"123");
        assert_eq!(tee.1, b"123");

        tee.unread_u8(b'0');
        assert_eq!(*tee.0.0, b"123");
        assert_eq!(tee.1, b"0123");

        assert_eq!(tee.into_bytes(), b"0");
    }

    #[test]
    fn tee_nested() {
        //
        // `OwnedTee`
        //
        let mut reader = Bytes::from_static(b"0123456789");
        {
            let mut tee = reader.tee();
            assert_eq!(tee.read_u8(), Ok(b'0'));
            {
                let mut tee = tee.tee();
                assert_eq!(tee.read_u8(), Ok(b'1'));
                {
                    let mut tee = tee.tee();
                    assert_eq!(tee.read_u8(), Ok(b'2'));
                    assert_eq!(&*tee.into_bytes(), b"2");
                }
                assert_eq!(tee.read_u8(), Ok(b'3'));
                assert_eq!(&*tee.into_bytes(), b"123");
            }
            assert_eq!(tee.read_u8(), Ok(b'4'));
            assert_eq!(&*tee.into_bytes(), b"01234");
        }

        //
        // `BorrowedTee`
        //
        let mut reader = b"0123456789".as_slice();
        let mut reader = SliceReader::new(&mut reader);
        {
            let mut tee = reader.tee();
            assert_eq!(tee.read_u8(), Ok(b'0'));
            {
                let mut tee = tee.tee();
                assert_eq!(tee.read_u8(), Ok(b'1'));
                {
                    let mut tee = tee.tee();
                    assert_eq!(tee.read_u8(), Ok(b'2'));
                    assert_eq!(tee.into_bytes(), b"2");
                }
                assert_eq!(tee.read_u8(), Ok(b'3'));
                assert_eq!(tee.into_bytes(), b"123");
            }
            assert_eq!(tee.read_u8(), Ok(b'4'));
            assert_eq!(tee.into_bytes(), b"01234");
        }
    }

    #[test]
    fn read_first_token() {
        assert_eq!(
            read_ext(b"0").read_first_token(),
            Ok(Token::ByteString(b'0')),
        );
        assert_eq!(read_ext(b"le").read_first_token(), Ok(Token::List));
        assert_eq!(read_ext(b"").read_first_token(), Err(Error::Eof));
    }

    #[test]
    fn read_token() {
        assert_eq!(read_ext(b"0").read_token(), Ok(Token::ByteString(b'0')));
        assert_eq!(read_ext(b"le").read_token(), Ok(Token::List));
        assert_eq!(read_ext(b"").read_token(), Err(Error::Incomplete));
    }

    #[test]
    fn read_item_token() {
        assert_eq!(
            read_ext(b"0").read_item_token(),
            Ok(Some(Token::ByteString(b'0'))),
        );
        assert_eq!(read_ext(b"le").read_item_token(), Ok(Some(Token::List)));
        assert_eq!(read_ext(b"e").read_item_token(), Ok(None));
        assert_eq!(read_ext(b"").read_item_token(), Err(Error::Incomplete));
    }

    #[test]
    fn read_byte_string() {
        assert_eq!(read_ext(b":").read_byte_string(b'0'), Ok(vec![]));
        assert_eq!(
            read_ext(b":\x00\x01").read_byte_string(b'2'),
            Ok(vec![0, 1]),
        );
        assert_eq!(
            read_ext(b"0:abcdefghij").read_byte_string(b'1'),
            Ok(b"abcdefghij".to_vec()),
        );

        assert_eq!(read_ext(b"").read_byte_string(b'1'), Err(Error::Incomplete));
        assert_eq!(
            read_ext(b"23").read_byte_string(b'1'),
            Err(Error::Incomplete),
        );
        assert_eq!(
            read_ext(&[b'0'; INTEGER_BUF_SIZE - 1]).read_byte_string(b'1'),
            Err(Error::Incomplete),
        );

        assert_matches!(
            read_ext(&[b'0'; INTEGER_BUF_SIZE]).read_byte_string(b'1'),
            Err(Error::IntegerBufferOverflow { .. }),
        );

        let testdata = std::format!("{}:", u128::try_from(usize::MAX).unwrap() + 1);
        let testdata = testdata.as_bytes();
        assert_matches!(
            read_ext(&testdata[1..]).read_byte_string(testdata[0]),
            Err(Error::IntegerOverflow { .. }),
        );

        assert_matches!(
            read_ext(b":").read_byte_string(b'1'),
            Err(Error::Incomplete),
        );
        assert_matches!(
            read_ext(b":a").read_byte_string(b'2'),
            Err(Error::Incomplete),
        );
        assert_matches!(
            read_ext(b"2:abcdefghijk").read_byte_string(b'1'),
            Err(Error::Incomplete),
        );
    }

    #[test]
    fn read_integer() {
        assert_eq!(read_ext(b"0e").read_integer(), Ok(0u8));
        assert_eq!(read_ext(b"-1e").read_integer(), Ok(-1i8));

        assert_eq!(read_ext(b"").read_integer::<u8>(), Err(Error::Incomplete));
        assert_eq!(read_ext(b"23").read_integer::<u8>(), Err(Error::Incomplete));
        assert_eq!(
            read_ext(&[b'1'; INTEGER_BUF_SIZE]).read_integer::<u8>(),
            Err(Error::Incomplete),
        );

        assert_matches!(
            read_ext(&[b'1'; INTEGER_BUF_SIZE + 1]).read_integer::<u8>(),
            Err(Error::IntegerBufferOverflow { .. }),
        );

        assert_matches!(
            read_ext(b"e").read_integer::<u8>(),
            Err(Error::StrictInteger { .. }),
        );
        assert_matches!(
            read_ext(b"-0e").read_integer::<u8>(),
            Err(Error::StrictInteger { .. }),
        );
        assert_matches!(
            read_ext(b"01e").read_integer::<u8>(),
            Err(Error::StrictInteger { .. }),
        );

        assert_matches!(
            read_ext(b"257e").read_integer::<u8>(),
            Err(Error::IntegerOverflow { .. }),
        );
        assert_matches!(
            read_ext(b"-129e").read_integer::<i8>(),
            Err(Error::IntegerOverflow { .. }),
        );
        assert_matches!(
            read_ext(b"-1e").read_integer::<u8>(),
            Err(Error::IntegerOverflow { .. }),
        );
    }

    #[test]
    fn token() {
        fn test(prefix: u8, token: Token) {
            assert_eq!(Token::new(prefix), Ok(token.clone()));
            assert_eq!(token.to_prefix(), prefix);
        }

        test(b'0', Token::ByteString(b'0'));
        test(b'1', Token::ByteString(b'1'));
        test(b'2', Token::ByteString(b'2'));
        test(b'3', Token::ByteString(b'3'));
        test(b'4', Token::ByteString(b'4'));
        test(b'5', Token::ByteString(b'5'));
        test(b'6', Token::ByteString(b'6'));
        test(b'7', Token::ByteString(b'7'));
        test(b'8', Token::ByteString(b'8'));
        test(b'9', Token::ByteString(b'9'));
        test(b'i', Token::Integer);
        test(b'l', Token::List);
        test(b'd', Token::Dictionary);

        assert_matches!(Token::new(b'\x00'), Err(Error::Prefix { .. }));
        assert_matches!(Token::new(b'e'), Err(Error::Prefix { .. }));
        assert_matches!(Token::new(b'-'), Err(Error::Prefix { .. }));
    }
}
