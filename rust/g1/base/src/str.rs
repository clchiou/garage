use std::cmp;
use std::num::ParseIntError;
use std::str::{self, FromStr};

pub trait StrExt {
    // TODO: Deprecate this when/if the `str` type provides a `chunks` method.
    fn chunks(&self, chunk_size: usize) -> impl Iterator<Item = &str>;

    // Helper function for using `str::make_ascii_lowercase`.
    fn transform<'a, F>(&self, buffer: &'a mut [u8], f: F) -> Option<&'a str>
    where
        F: FnOnce(&mut str) -> Option<&str>;
}

impl StrExt for str {
    fn chunks(&self, chunk_size: usize) -> impl Iterator<Item = &str> {
        assert!(chunk_size != 0);
        (0..self.len())
            .step_by(chunk_size)
            .map(move |i| &self[i..cmp::min(i + chunk_size, self.len())])
    }

    fn transform<'a, F>(&self, buffer: &'a mut [u8], f: F) -> Option<&'a str>
    where
        F: FnOnce(&mut str) -> Option<&str>,
    {
        let input = self.as_bytes();
        let buffer = buffer.get_mut(0..input.len())?;
        buffer.copy_from_slice(input);
        let buffer = unsafe { str::from_utf8_unchecked_mut(buffer) };
        f(buffer)
    }
}

/// Parses a hex string.
#[derive(Debug)]
pub struct Hex<T>(pub T);

impl<T> Hex<T> {
    pub fn into_inner(self) -> T {
        self.0
    }
}

impl<T> FromStr for Hex<T>
where
    T: FromIterator<u8>,
{
    type Err = ParseIntError;

    fn from_str(hex: &str) -> Result<Self, Self::Err> {
        // TODO: Should we disallow odd length of `hex`?
        Ok(Hex(hex
            .chunks(2)
            .map(|byte| u8::from_str_radix(byte, 16))
            .try_collect()?))
    }
}

// TODO: Is it possible to implement `FromStr` for `Hex<[u8; N]>` using specialization?
impl<'a, const N: usize> TryFrom<&'a str> for Hex<[u8; N]> {
    type Error = &'a str;

    // NOTE: We disallow odd length of `hex` here.
    fn try_from(hex: &'a str) -> Result<Self, Self::Error> {
        if hex.len() != N * 2 {
            return Err(hex);
        }
        let mut array = [0u8; N];
        for (p, byte) in array.iter_mut().zip(hex.chunks(2)) {
            *p = u8::from_str_radix(byte, 16).map_err(|_| hex)?;
        }
        Ok(Hex(array))
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use super::*;

    #[test]
    #[should_panic(expected = "assertion failed: chunk_size != 0")]
    fn zero_chunk_size() {
        let _ = "".chunks(0);
    }

    #[test]
    fn chunks() {
        fn test(string: &str, chunk_size: usize, expect: Vec<&str>) {
            assert_eq!(string.chunks(chunk_size).collect::<Vec<_>>(), expect);
        }

        test("", 1, Vec::new());

        test("a", 1, vec!["a"]);
        test("ab", 1, vec!["a", "b"]);
        test("abc", 1, vec!["a", "b", "c"]);

        test("a", 2, vec!["a"]);
        test("ab", 2, vec!["ab"]);
        test("abc", 2, vec!["ab", "c"]);
        test("abcd", 2, vec!["ab", "cd"]);
        test("abcdf", 2, vec!["ab", "cd", "f"]);
    }

    #[test]
    fn transform() {
        assert_eq!(
            "ABC".transform(&mut [0u8; 32], |x| {
                x.make_ascii_lowercase();
                Some(&*x)
            }),
            Some("abc"),
        );

        assert_eq!(
            "ABC".transform(&mut [0u8; 2], |x| {
                x.make_ascii_lowercase();
                Some(&*x)
            }),
            None,
        );

        assert_eq!("ABC".transform(&mut [0u8; 32], |_| None), None);
    }

    #[test]
    fn hex_vec() {
        fn test(hex: &str, expect: Vec<u8>) {
            assert_matches!(hex.parse::<Hex<Vec<u8>>>(), Ok(Hex(v)) if v == expect);
        }

        test("", vec![]);

        test("0", vec![0]);
        test("00", vec![0]);
        test("000", vec![0, 0]);

        test("1", vec![0x01]); // NOTE: It is 0x01, not 0x10.
        test("12", vec![0x12]);
        test("123", vec![0x12, 0x03]); // NOTE: It is 0x03, not 0x30.
        test("1234", vec![0x12, 0x34]);

        test("deadbeef", vec![0xde, 0xad, 0xbe, 0xef]);

        assert_matches!("x".parse::<Hex<Vec<u8>>>(), Err(_));
    }

    #[test]
    fn hex_array() {
        fn test<const N: usize>(hex: &str, expect: [u8; N]) {
            assert_matches!(hex.try_into(), Ok(Hex(v)) if v == expect);
        }

        test("", []);

        test("00", [0]);
        assert_matches!(Hex::<[u8; 1]>::try_from("0"), Err("0"));
        assert_matches!(Hex::<[u8; 1]>::try_from("000"), Err("000"));

        test("12", [0x12]);
        test("1234", [0x12, 0x34]);
        test("deadbeef", [0xde, 0xad, 0xbe, 0xef]);

        assert_matches!(Hex::<[u8; 1]>::try_from("xx"), Err("xx"));
    }
}
