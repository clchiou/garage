use std::cmp;
use std::num::ParseIntError;
use std::str::FromStr;

pub trait StrExt {
    // TODO: Deprecate this when/if the `str` type provides a `chunks` method.
    fn chunks(&self, chunk_size: usize) -> impl Iterator<Item = &str>;
}

impl StrExt for str {
    fn chunks(&self, chunk_size: usize) -> impl Iterator<Item = &str> {
        assert!(chunk_size != 0);
        (0..self.len())
            .step_by(chunk_size)
            .map(move |i| &self[i..cmp::min(i + chunk_size, self.len())])
    }
}

/// Parses a hex string.
#[derive(Debug)]
pub struct Hex<T>(pub T);

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
    fn hex() {
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
}
