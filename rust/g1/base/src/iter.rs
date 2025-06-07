use std::borrow::Cow;
use std::cmp::Ordering;
use std::error;
use std::fmt;
use std::iter::Peekable;

/// Extends the `std::iter::Iterator` trait.
pub trait IteratorExt: Iterator {
    fn collect_then_sort(self) -> Vec<Self::Item>
    where
        Self: Sized,
        Self::Item: Ord,
    {
        let mut items: Vec<_> = self.collect();
        items.sort();
        items
    }

    fn collect_then_sort_by<F>(self, compare: F) -> Vec<Self::Item>
    where
        Self: Sized,
        F: FnMut(&Self::Item, &Self::Item) -> Ordering,
    {
        let mut items: Vec<_> = self.collect();
        items.sort_by(compare);
        items
    }

    fn collect_then_sort_by_key<K, F>(self, to_key: F) -> Vec<Self::Item>
    where
        Self: Sized,
        F: FnMut(&Self::Item) -> K,
        K: Ord,
    {
        let mut items: Vec<_> = self.collect();
        items.sort_by_key(to_key);
        items
    }
}

impl<T> IteratorExt for T where T: Iterator {}

pub fn product<'a, XS, YS, X, Y>(xs: XS, ys: YS) -> impl Iterator<Item = (&'a X, &'a Y)>
where
    XS: IntoIterator<Item = &'a X>,
    YS: IntoIterator<Item = &'a Y>,
    <YS as IntoIterator>::IntoIter: Clone,
    X: 'a,
    Y: 'a,
{
    let xs = xs.into_iter();
    let ys = ys.into_iter();
    xs.flat_map(move |x| ys.clone().map(move |y| (x, y)))
}

//
// arbitrary byte string --escape--> printable ASCII byte string
//                       <-unescape-
//
/// Inverse of `<[u8]>::escape_ascii`.
#[derive(Clone, Debug)]
pub struct UnescapeAscii<I>(Peekable<I>)
where
    I: Iterator<Item = u8>;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UnescapeAsciiError(Cow<'static, str>);

impl fmt::Display for UnescapeAsciiError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl error::Error for UnescapeAsciiError {}

impl<I> UnescapeAscii<I>
where
    I: Iterator<Item = u8>,
{
    pub fn new(iter: I) -> Self {
        Self(iter.peekable())
    }
}

macro_rules! uaerr {
    ($msg:literal $(,)?) => {
        UnescapeAsciiError($msg.into())
    };

    ($msg:literal, $arg:expr $(,)?) => {
        UnescapeAsciiError(std::format!($msg, $arg.escape_ascii()).into())
    };
}

impl<I> Iterator for UnescapeAscii<I>
where
    I: Iterator<Item = u8>,
{
    type Item = Result<u8, UnescapeAsciiError>;

    fn next(&mut self) -> Option<Self::Item> {
        self.0.next().map(|c| match c {
            b'\\' => self.unescape(),
            0x00..=0x1f | 0x7f..=0xff => Err(uaerr!("expect printable character: '{}'", c)),
            _ => Ok(c),
        })
    }

    fn size_hint(&self) -> (usize, Option<usize>) {
        let (lower, upper) = self.0.size_hint();
        (lower / 4, upper)
    }
}

impl<I> UnescapeAscii<I>
where
    I: Iterator<Item = u8>,
{
    fn unescape(&mut self) -> Result<u8, UnescapeAsciiError> {
        let b = match self.try_peek(|| uaerr!("expect escape sequence"))? {
            b't' => b'\t',
            b'r' => b'\r',
            b'n' => b'\n',
            b'\\' => b'\\',
            b'\'' => b'\'',
            b'"' => b'"',
            b'x' => {
                self.0.next();
                let h = hex_digit(self.try_peek(|| uaerr!("expect high nibble"))?)?;
                self.0.next();
                let l = hex_digit(self.try_peek(|| uaerr!("expect low nibble"))?)?;
                (h << 4) | l
            }
            c => return Err(uaerr!("expect special character: '{}'", c)),
        };
        self.0.next();
        Ok(b)
    }

    fn try_peek<F>(&mut self, err: F) -> Result<u8, UnescapeAsciiError>
    where
        F: FnOnce() -> UnescapeAsciiError,
    {
        self.0.peek().copied().ok_or_else(err)
    }
}

fn hex_digit(c: u8) -> Result<u8, UnescapeAsciiError> {
    match c {
        b'0'..=b'9' => Ok(c - b'0'),
        b'a'..=b'f' => Ok(c - b'a' + 10),
        b'A'..=b'F' => Ok(c - b'A' + 10),
        _ => Err(uaerr!("expect hex digit: '{}'", c)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn collect_then_sort() {
        assert_eq!([3, 1, 2].into_iter().collect_then_sort(), vec![1, 2, 3]);
        assert_eq!(
            [3, 1, 2].into_iter().collect_then_sort_by(|x, y| x.cmp(y)),
            vec![1, 2, 3],
        );
        assert_eq!(
            [3, 1, 2].into_iter().collect_then_sort_by_key(|x| *x),
            vec![1, 2, 3],
        );
    }

    #[test]
    fn test_product() {
        fn test<const N: usize>(xs: &[usize], ys: &[usize], expect: [(usize, usize); N]) {
            assert_eq!(
                product(xs, ys).map(|(x, y)| (*x, *y)).collect::<Vec<_>>(),
                expect,
            );
        }

        test(&[], &[], []);
        test(&[1], &[], []);
        test(&[], &[10], []);
        test(&[1], &[10], [(1, 10)]);
        test(&[1, 2], &[10], [(1, 10), (2, 10)]);
        test(&[1], &[10, 20], [(1, 10), (1, 20)]);
        test(&[1, 2], &[10, 20], [(1, 10), (1, 20), (2, 10), (2, 20)]);
    }

    #[test]
    fn unescape_ascii() {
        fn test_ok(testdata: &[u8]) {
            assert_eq!(
                UnescapeAscii::new(testdata.escape_ascii()).try_collect::<Vec<u8>>(),
                Ok(testdata.to_vec()),
            );
        }

        fn test_err(testdata: &[u8], expect: &[Result<u8, UnescapeAsciiError>]) {
            assert_eq!(
                UnescapeAscii::new(testdata.iter().copied()).collect::<Vec<_>>(),
                expect,
            );
        }

        test_ok(b"");
        test_ok(b"Hello, World!");
        test_ok(b"\t\r\n\\'\"");
        test_ok("a\u{fffd}b".as_bytes());
        test_ok("你好，世界！".as_bytes());

        test_ok(b"\x00\x01\x02\x03\x04\x05\x06\x07 \x08\x09\x0a\x0b\x0c\x0d\x0e\x0f");
        test_ok(b"\x10\x11\x12\x13\x14\x15\x16\x17 \x18\x19\x1a\x1b\x1c\x1d\x1e\x1f");
        test_ok(b"\x20\x21\x22\x23\x24\x25\x26\x27 \x28\x29\x2a\x2b\x2c\x2d\x2e\x2f");
        test_ok(b"\x30\x31\x32\x33\x34\x35\x36\x37 \x38\x39\x3a\x3b\x3c\x3d\x3e\x3f");
        test_ok(b"\x40\x41\x42\x43\x44\x45\x46\x47 \x48\x49\x4a\x4b\x4c\x4d\x4e\x4f");
        test_ok(b"\x50\x51\x52\x53\x54\x55\x56\x57 \x58\x59\x5a\x5b\x5c\x5d\x5e\x5f");
        test_ok(b"\x60\x61\x62\x63\x64\x65\x66\x67 \x68\x69\x6a\x6b\x6c\x6d\x6e\x6f");
        test_ok(b"\x70\x71\x72\x73\x74\x75\x76\x77 \x78\x79\x7a\x7b\x7c\x7d\x7e\x7f");

        test_ok(b"\x80\x81\x82\x83\x84\x85\x86\x87 \x88\x89\x8a\x8b\x8c\x8d\x8e\x8f");
        test_ok(b"\x90\x91\x92\x93\x94\x95\x96\x97 \x98\x99\x9a\x9b\x9c\x9d\x9e\x9f");
        test_ok(b"\xa0\xa1\xa2\xa3\xa4\xa5\xa6\xa7 \xa8\xa9\xaa\xab\xac\xad\xae\xaf");
        test_ok(b"\xb0\xb1\xb2\xb3\xb4\xb5\xb6\xb7 \xb8\xb9\xba\xbb\xbc\xbd\xbe\xbf");
        test_ok(b"\xc0\xc1\xc2\xc3\xc4\xc5\xc6\xc7 \xc8\xc9\xca\xcb\xcc\xcd\xce\xcf");
        test_ok(b"\xd0\xd1\xd2\xd3\xd4\xd5\xd6\xd7 \xd8\xd9\xda\xdb\xdc\xdd\xde\xdf");
        test_ok(b"\xe0\xe1\xe2\xe3\xe4\xe5\xe6\xe7 \xe8\xe9\xea\xeb\xec\xed\xee\xef");
        test_ok(b"\xf0\xf1\xf2\xf3\xf4\xf5\xf6\xf7 \xf8\xf9\xfa\xfb\xfc\xfd\xfe\xff");

        test_err(br#"a\"#, &[Ok(b'a'), Err(uaerr!("expect escape sequence"))]);
        test_err(br#"a\x"#, &[Ok(b'a'), Err(uaerr!("expect high nibble"))]);
        test_err(br#"a\x0"#, &[Ok(b'a'), Err(uaerr!("expect low nibble"))]);
        test_err(
            br#"a\xy0"#,
            &[
                Ok(b'a'),
                Err(uaerr!("expect hex digit: 'y'")),
                Ok(b'y'),
                Ok(b'0'),
            ],
        );
        test_err(
            br#"a\x0Z"#,
            &[Ok(b'a'), Err(uaerr!("expect hex digit: 'Z'")), Ok(b'Z')],
        );
        test_err(
            br#"a\X01"#,
            &[
                Ok(b'a'),
                Err(uaerr!("expect special character: 'X'")),
                Ok(b'X'),
                Ok(b'0'),
                Ok(b'1'),
            ],
        );
        test_err(
            b"a\x00b",
            &[
                Ok(b'a'),
                Err(uaerr!("expect printable character: '\\x00'")),
                Ok(b'b'),
            ],
        );
    }

    #[test]
    fn test_hex_digit() {
        for (c, d) in [
            (b'0', 0),
            (b'1', 1),
            (b'2', 2),
            (b'3', 3),
            (b'4', 4),
            (b'5', 5),
            (b'6', 6),
            (b'7', 7),
            (b'8', 8),
            (b'9', 9),
            (b'a', 10),
            (b'b', 11),
            (b'c', 12),
            (b'd', 13),
            (b'e', 14),
            (b'f', 15),
            (b'A', 10),
            (b'B', 11),
            (b'C', 12),
            (b'D', 13),
            (b'E', 14),
            (b'F', 15),
        ] {
            assert_eq!(hex_digit(c), Ok(d));
        }

        assert_eq!(hex_digit(b'G'), Err(uaerr!("expect hex digit: 'G'")));
        assert_eq!(hex_digit(b'h'), Err(uaerr!("expect hex digit: 'h'")));
    }
}
