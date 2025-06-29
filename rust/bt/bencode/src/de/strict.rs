use std::any;
use std::assert_matches::assert_matches;
use std::num::IntErrorKind;

use bytes::Bytes;
use snafu::prelude::*;

use crate::error::{Error, IntegerSnafu, StrictDictionaryKeySnafu, StrictIntegerSnafu};
use crate::int::Int;

pub(crate) trait Strictness {
    fn ensure_integer(integer: &[u8]) -> Result<(), Error>;

    fn ensure_dictionary_key(last_key: &Bytes, key: &Bytes) -> Result<(), Error>;

    fn parse_integer<I>(integer: &[u8]) -> Result<I, Error>
    where
        I: Int,
    {
        Self::ensure_integer(integer)?;
        unsafe { str::from_utf8_unchecked(integer) }
            .parse::<I>()
            .map_err(|error| {
                assert_matches!(
                    error.kind(),
                    IntErrorKind::InvalidDigit
                        | IntErrorKind::NegOverflow
                        | IntErrorKind::PosOverflow,
                );
                Error::IntegerOverflow {
                    int_type_name: any::type_name::<I>(),
                    integer: Bytes::copy_from_slice(integer),
                }
            })
    }
}

pub(super) struct Strict;

impl Strictness for Strict {
    fn ensure_integer(integer: &[u8]) -> Result<(), Error> {
        ensure!(
            lazy_regex::regex_is_match!(r#"(?x-u) ^ (?: 0 | -? [1-9] \d* ) $ "#B, integer),
            StrictIntegerSnafu {
                integer: Bytes::copy_from_slice(integer),
            },
        );
        Ok(())
    }

    fn ensure_dictionary_key(last_key: &Bytes, key: &Bytes) -> Result<(), Error> {
        ensure!(
            last_key < key,
            StrictDictionaryKeySnafu {
                last_key: last_key.clone(),
                key: key.clone(),
            },
        );
        Ok(())
    }
}

pub(super) struct NonStrict;

impl Strictness for NonStrict {
    fn ensure_integer(integer: &[u8]) -> Result<(), Error> {
        ensure!(
            lazy_regex::regex_is_match!(r"(?x-u) ^ -? \d+ $ "B, integer),
            IntegerSnafu {
                integer: Bytes::copy_from_slice(integer),
            },
        );
        Ok(())
    }

    fn ensure_dictionary_key(_last_key: &Bytes, _key: &Bytes) -> Result<(), Error> {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use super::*;

    #[test]
    fn ensure_integer() {
        for testdata in [b"0".as_slice(), b"1", b"23456789", b"-1", b"-9876543210"] {
            assert_eq!(Strict::ensure_integer(testdata), Ok(()));
            assert_eq!(NonStrict::ensure_integer(testdata), Ok(()));
        }

        for testdata in [b"".as_slice(), b" ", b"\x00", b" 1", b"1 ", b"1,0", b"- 1"] {
            assert_matches!(
                Strict::ensure_integer(testdata),
                Err(Error::StrictInteger { .. })
            );
            assert_matches!(
                NonStrict::ensure_integer(testdata),
                Err(Error::Integer { .. })
            );
        }

        for testdata in [b"00".as_slice(), b"-0", b"01", b"-02"] {
            assert_matches!(
                Strict::ensure_integer(testdata),
                Err(Error::StrictInteger { .. })
            );
            assert_eq!(NonStrict::ensure_integer(testdata), Ok(()));
        }
    }

    #[test]
    fn parse_integer() {
        assert_eq!(Strict::parse_integer(b"0"), Ok(0u8));
        assert_eq!(Strict::parse_integer(b"123"), Ok(123u8));
        assert_eq!(NonStrict::parse_integer(b"0"), Ok(0u8));
        assert_eq!(NonStrict::parse_integer(b"123"), Ok(123u8));

        assert_matches!(
            Strict::parse_integer::<u8>(b"456"),
            Err(Error::IntegerOverflow { .. }),
        );
        assert_matches!(
            Strict::parse_integer::<i8>(b"-789"),
            Err(Error::IntegerOverflow { .. }),
        );
        assert_matches!(
            NonStrict::parse_integer::<u8>(b"456"),
            Err(Error::IntegerOverflow { .. }),
        );
        assert_matches!(
            NonStrict::parse_integer::<i8>(b"-789"),
            Err(Error::IntegerOverflow { .. }),
        );

        assert_matches!(
            Strict::parse_integer::<u8>(b"-1"),
            Err(Error::IntegerOverflow { .. }),
        );
        assert_matches!(
            NonStrict::parse_integer::<u8>(b"-1"),
            Err(Error::IntegerOverflow { .. }),
        );

        assert_matches!(
            Strict::parse_integer::<u8>(b"012"),
            Err(Error::StrictInteger { .. }),
        );
        assert_matches!(
            Strict::parse_integer::<u8>(b"-0"),
            Err(Error::StrictInteger { .. }),
        );
        assert_eq!(NonStrict::parse_integer(b"012"), Ok(12i8));
        assert_eq!(NonStrict::parse_integer(b"-0"), Ok(0i8));
    }

    #[test]
    fn ensure_dictionary_key() {
        let key0 = Bytes::from_static(b"aaa");
        let key1 = Bytes::from_static(b"bb");

        assert_eq!(Strict::ensure_dictionary_key(&key0, &key1), Ok(()));
        assert_eq!(NonStrict::ensure_dictionary_key(&key0, &key1), Ok(()));

        assert_matches!(
            Strict::ensure_dictionary_key(&key1, &key0),
            Err(Error::StrictDictionaryKey { .. }),
        );
        assert_eq!(NonStrict::ensure_dictionary_key(&key1, &key0), Ok(()));

        assert_matches!(
            Strict::ensure_dictionary_key(&key0, &key0),
            Err(Error::StrictDictionaryKey { .. }),
        );
        assert_eq!(NonStrict::ensure_dictionary_key(&key0, &key0), Ok(()));
    }
}
