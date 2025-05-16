//! Extends the `bytes` crate.

use std::fmt;
use std::io::Write;
use std::mem;

use bytes::{Buf, BufMut, TryGetError};
use paste::paste;

pub use g1_bytes_derive::{BufExt, BufMutExt, BufPeekExt};

macro_rules! gen_peek {
    ($type:ident $($endian:ident)*) => {
        paste! {
            gen_peek!(@ [<peek_ $type>] [<get_ $type>] $type);
            $(gen_peek!(@ [<peek_ $type _ $endian>] [<get_ $type _ $endian>] $type);)*
        }
    };

    (@ $peek:ident $get:ident $type:ident) => {
        fn $peek(&self) -> Result<$type, TryGetError> {
            self.peek_slice(mem::size_of::<$type>()).map(|mut slice| slice.$get())
        }
    };
}

macro_rules! gen_peek_int {
    ($name:ident $type:ident $($endian:ident)*) => {
        paste! {
            gen_peek_int!(@ [<peek_ $name>] [<get_ $name>] $type);
            $(gen_peek_int!(@ [<peek_ $name _ $endian>] [<get_ $name _ $endian>] $type);)*
        }
    };

    (@ $peek:ident $get:ident $type:ident) => {
        fn $peek(&self, nbytes: usize) -> Result<$type, TryGetError> {
            self.peek_slice(nbytes).map(|mut slice| slice.$get(nbytes))
        }
    };
}

/// Provides `peek_X` methods.
///
/// We cannot implement `BufPeekExt` for `Buf` types because `Buf::chunk` only returns the current
/// chunk, which may contain less than the full buffer data.
pub trait BufPeekExt {
    gen_peek!(u8);
    gen_peek!(i8);
    gen_peek!(u16 le ne);
    gen_peek!(i16 le ne);
    gen_peek!(u32 le ne);
    gen_peek!(i32 le ne);
    gen_peek!(u64 le ne);
    gen_peek!(i64 le ne);
    gen_peek!(u128 le ne);
    gen_peek!(i128 le ne);
    gen_peek_int!(uint u64 le ne);
    gen_peek_int!(int i64 le ne);
    gen_peek!(f32 le ne);
    gen_peek!(f64 le ne);

    fn peek_slice(&self, size: usize) -> Result<&[u8], TryGetError>;

    /// Returns a slice whose last byte matches the `predicate`.
    fn peek_slice_until<Predicate>(&self, predicate: Predicate) -> Option<&[u8]>
    where
        Predicate: FnMut(&u8) -> bool;

    /// It is similar to `peek_slice_until`, except that the last byte of the returned slice is
    /// stripped off.
    fn peek_slice_until_strip<Predicate>(&self, predicate: Predicate) -> Option<&[u8]>
    where
        Predicate: FnMut(&u8) -> bool,
    {
        self.peek_slice_until(predicate)
            .map(|slice| &slice[..slice.len() - 1])
    }
}

impl<T> BufPeekExt for T
where
    T: AsRef<[u8]>,
{
    fn peek_slice(&self, size: usize) -> Result<&[u8], TryGetError> {
        let slice = self.as_ref();
        if slice.len() < size {
            return Err(TryGetError {
                requested: size,
                available: slice.len(),
            });
        }
        Ok(&slice[..size])
    }

    fn peek_slice_until<Predicate>(&self, mut predicate: Predicate) -> Option<&[u8]>
    where
        Predicate: FnMut(&u8) -> bool,
    {
        self.as_ref()
            .split_inclusive(&mut predicate)
            .next()
            .filter(|slice| predicate(slice.last().unwrap()))
    }
}

/// Adds methods that allow certain `Buf` types to borrow slices from the buffer data.
///
/// `BufSliceExt` differs from `BufPeekExt` in that it advances the internal cursor of the buffer,
/// whereas `BufPeekExt` does not.  The implementers of `BufSliceExt` have to ensure that the
/// borrowed slices preceding the cursor remain valid.
pub trait BufSliceExt: Buf {
    /// Creates a buffer that shares the same underlying storage but has a separate buffer cursor.
    ///
    /// The cursor of the returned buffer and that of the original buffer may advance separately.
    fn dup(&self) -> Self;

    fn get_slice<'a>(&mut self, size: usize) -> &'a [u8]
    where
        Self: 'a;

    fn try_get_slice<'a>(&mut self, size: usize) -> Result<&'a [u8], TryGetError>
    where
        Self: 'a,
    {
        if self.remaining() < size {
            return Err(TryGetError {
                requested: size,
                available: self.remaining(),
            });
        }
        Ok(self.get_slice(size))
    }

    /// Returns a slice whose last byte matches the `predicate`.
    fn get_slice_until<'a, Predicate>(&mut self, predicate: Predicate) -> Option<&'a [u8]>
    where
        Self: 'a,
        Predicate: FnMut(&u8) -> bool;

    /// It is similar to `get_slice_until`, except that the last byte of the returned slice is
    /// stripped off.
    fn get_slice_until_strip<'a, Predicate>(&mut self, predicate: Predicate) -> Option<&'a [u8]>
    where
        Self: 'a,
        Predicate: FnMut(&u8) -> bool,
    {
        self.get_slice_until(predicate)
            .map(|slice| &slice[..slice.len() - 1])
    }
}

impl BufSliceExt for &[u8] {
    fn dup(&self) -> Self {
        self
    }

    fn get_slice<'a>(&mut self, size: usize) -> &'a [u8]
    where
        Self: 'a,
    {
        let slice = &self[..size];
        self.advance(size);
        slice
    }

    fn get_slice_until<'a, Predicate>(&mut self, mut predicate: Predicate) -> Option<&'a [u8]>
    where
        Self: 'a,
        Predicate: FnMut(&u8) -> bool,
    {
        self.split_inclusive(&mut predicate)
            .next()
            .filter(|slice| predicate(slice.last().unwrap()))
            .inspect(|slice| self.advance(slice.len()))
    }
}

pub trait BufMutExt: BufMut {
    /// Formats a value using `fmt::Debug` and writes the output to the buffer.
    fn put_debug<T: fmt::Debug>(&mut self, value: &T) {
        write!(self.writer(), "{value:?}").expect("buffer write should be infallible");
    }

    /// It is similar to `put_debug` except that it uses `fmt::Display`.
    fn put_display<T: fmt::Display>(&mut self, value: &T) {
        write!(self.writer(), "{value}").expect("buffer write should be infallible");
    }
}

impl<T> BufMutExt for T where T: BufMut {}

#[cfg(test)]
mod tests {
    use super::*;

    fn ok(bytes: &[u8]) -> Result<&[u8], TryGetError> {
        Ok(bytes)
    }

    fn err<'a>(requested: usize, available: usize) -> Result<&'a [u8], TryGetError> {
        Err(TryGetError {
            requested,
            available,
        })
    }

    fn some(bytes: &[u8]) -> Option<&[u8]> {
        Some(bytes)
    }

    macro_rules! test_peek {
        ($array:expr, $expect:expr, ($($type:ident),+) $(,)?) => {
            paste! {
                $(
                    test_peek!($array, $expect => [<peek_ $type>]);
                    test_peek!($array, $type::swap_bytes($expect) => [<peek_ $type _le>]);
                    if cfg!(target_endian = "big") {
                        test_peek!($array, $expect => [<peek_ $type _ne>]);
                    } else {
                        test_peek!($array, $type::swap_bytes($expect) => [<peek_ $type _ne>]);
                    }
                )*
            }
        };

        ($array:expr, $expect:expr => $($peek:ident),+ $(,)?) => {
            $(
                let buf: &[u8] = &$array;
                assert_eq!(buf.$peek(), Ok($expect));
                assert_eq!(
                    (&buf[1..]).$peek(),
                    Err(TryGetError {
                        requested: buf.len(),
                        available: buf.len() - 1,
                    }),
                );
            )*
        };
    }

    #[test]
    fn peek() {
        test_peek!([1], 1 => peek_u8, peek_i8);

        test_peek!([1, 2], 0x0102, (u16, i16));
        test_peek!([1, 2, 3, 4], 0x01020304, (u32, i32));
        test_peek!([1, 2, 3, 4, 5, 6, 7, 8], 0x0102030405060708, (u64, i64));
        test_peek!(
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
            0x0102030405060708090a0b0c0d0e0f10,
            (u128, i128),
        );

        test_peek!([0, 0, 0, 0], 0f32 => peek_f32, peek_f32_le, peek_f32_ne);
        test_peek!([0, 0, 0, 0, 0, 0, 0, 0], 0f64 => peek_f64, peek_f64_le, peek_f64_ne);
    }

    macro_rules! test_peek_int {
        ($type:ident) => {
            paste! {
                test_peek_int!([<peek_ $type>], 0x010203);
                test_peek_int!([<peek_ $type _le>], 0x030201);
                if cfg!(target_endian = "big") {
                    test_peek_int!([<peek_ $type _ne>], 0x010203);
                } else {
                    test_peek_int!([<peek_ $type _ne>], 0x030201);
                }
            }
        };

        ($peek:ident, $expect:expr) => {
            paste! {
                let buf: &[u8] = &[1, 2, 3];
                assert_eq!(buf.$peek(3), Ok($expect));
                assert_eq!(
                    buf.$peek(4),
                    Err(TryGetError {
                        requested: 4,
                        available: 3,
                    }),
                );
            }
        };
    }

    #[test]
    fn peek_nbytes() {
        test_peek_int!(uint);
        test_peek_int!(int);
    }

    #[test]
    fn peek_slice() {
        fn test<F>(buffer: &[u8], mut predicate: F, expect: Option<&[u8]>)
        where
            F: FnMut(&u8) -> bool,
        {
            let expect_strip = expect.clone().map(|slice| &slice[..slice.len() - 1]);
            assert_eq!(buffer.peek_slice_until(&mut predicate), expect);
            assert_eq!(buffer.peek_slice_until_strip(&mut predicate), expect_strip);
        }

        let buffer = b"".as_slice();
        assert_eq!(buffer.peek_slice(0), ok(b""));
        assert_eq!(buffer.peek_slice(1), err(1, 0));
        assert_eq!(buffer.peek_slice_until(|_| true), None);
        assert_eq!(buffer.peek_slice_until(|_| false), None);
        assert_eq!(buffer.peek_slice_until_strip(|_| true), None);
        assert_eq!(buffer.peek_slice_until_strip(|_| false), None);

        let buffer = b"hello world".as_slice();
        assert_eq!(buffer.peek_slice(0), ok(b""));
        assert_eq!(buffer.peek_slice(1), ok(b"h"));
        assert_eq!(buffer.peek_slice(11), ok(b"hello world"));
        assert_eq!(buffer.peek_slice(12), err(12, 11));
        test(buffer, |x| *x == b' ', some(b"hello "));
        test(buffer, |x| *x == b'x', None);
        test(buffer, |_| true, some(b"h"));
        test(buffer, |_| false, None);
    }

    #[test]
    fn dup() {
        let mut buffer = b"hello world".as_slice();
        let mut dup = buffer.dup();
        assert_eq!(buffer, b"hello world");
        assert_eq!(dup, b"hello world");

        assert_eq!(buffer.get_slice(1), b"h".as_slice());
        assert_eq!(buffer, b"ello world");
        assert_eq!(dup, b"hello world");

        assert_eq!(dup.get_slice(3), b"hel".as_slice());
        assert_eq!(buffer, b"ello world");
        assert_eq!(dup, b"lo world");
    }

    #[test]
    #[should_panic(expected = "range end index 1 out of range for slice of length 0")]
    fn get_slice_panic() {
        let mut buffer = b"".as_slice();
        buffer.get_slice(1);
    }

    #[test]
    fn get_slice() {
        let mut buffer = b"".as_slice();
        assert_eq!(buffer.get_slice(0), b"");

        let mut buffer = b"hello world".as_slice();
        assert_eq!(buffer.get_slice(5), b"hello");
        assert_eq!(buffer, b" world");
    }

    #[test]
    fn try_get_slice() {
        let mut buffer = b"".as_slice();
        assert_eq!(buffer.try_get_slice(0), ok(b""));
        assert_eq!(buffer, b"");
        assert_eq!(buffer.try_get_slice(1), err(1, 0));
        assert_eq!(buffer, b"");

        let mut buffer = b"hello world".as_slice();
        assert_eq!(buffer.try_get_slice(5), ok(b"hello"));
        assert_eq!(buffer, b" world");
        assert_eq!(buffer.try_get_slice(7), err(7, 6));
        assert_eq!(buffer, b" world");
    }

    #[test]
    fn get_slice_until() {
        fn test<const N: usize, F>(data: &[u8; N], mut predicate: F, expect: Option<&[u8]>)
        where
            F: FnMut(&u8) -> bool,
        {
            let expect_strip = expect.clone().map(|slice| &slice[..slice.len() - 1]);

            let mut buffer = data.as_slice();
            assert_eq!(buffer.get_slice_until(&mut predicate), expect);
            match expect {
                Some(expect) => assert_eq!(buffer, &data[expect.len()..]),
                None => assert_eq!(buffer, data),
            }

            let mut buffer = data.as_slice();
            assert_eq!(buffer.get_slice_until_strip(&mut predicate), expect_strip);
            match expect {
                Some(expect) => assert_eq!(buffer, &data[expect.len()..]),
                None => assert_eq!(buffer, data),
            }
        }

        let mut buffer = b"".as_slice();
        assert_eq!(buffer.get_slice_until(|_| true), None);
        assert_eq!(buffer.get_slice_until(|_| false), None);
        assert_eq!(buffer.get_slice_until_strip(|_| true), None);
        assert_eq!(buffer.get_slice_until_strip(|_| false), None);

        let data = b"hello world";
        test(&data, |x| *x == b' ', some(b"hello "));
        test(&data, |x| *x == b'x', None);
        test(&data, |_| true, some(b"h"));
        test(&data, |_| false, None);
    }

    struct FmtError;

    impl fmt::Debug for FmtError {
        fn fmt(&self, _: &mut fmt::Formatter<'_>) -> fmt::Result {
            Err(Default::default())
        }
    }

    impl fmt::Display for FmtError {
        fn fmt(&self, _: &mut fmt::Formatter<'_>) -> fmt::Result {
            Err(Default::default())
        }
    }

    #[test]
    fn put_debug() {
        let mut buffer = Vec::new();
        buffer.put_debug(&"hello world");
        assert_eq!(&buffer, b"\"hello world\"");
    }

    #[test]
    fn put_display() {
        let mut buffer = Vec::new();
        buffer.put_display(&"hello world");
        assert_eq!(&buffer, b"hello world");
    }

    // After [commit], `write!` panics in case of formatting errors instead of returning an `io`
    // error.
    //
    // [commit] https://github.com/rust-lang/rust/commit/e00f27b7be9084e548f7197325c2f343e8ad27b9
    #[test]
    #[should_panic(
        expected = "a formatting trait implementation returned an error when the underlying stream did not"
    )]
    fn put_debug_panic() {
        let mut buffer = Vec::new();
        buffer.put_debug(&FmtError);
    }

    // Ditto.
    #[test]
    #[should_panic(
        expected = "a formatting trait implementation returned an error when the underlying stream did not"
    )]
    fn put_display_panic() {
        let mut buffer = Vec::new();
        buffer.put_display(&FmtError);
    }
}
