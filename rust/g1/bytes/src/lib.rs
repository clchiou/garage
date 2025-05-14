//! Extends the `bytes` crate.

use std::fmt;
use std::io::Write;
use std::mem;

use bytes::{Buf, BufMut};
use paste::paste;

pub use g1_bytes_derive::{BufExt, BufMutExt, BufPeekExt};

macro_rules! for_each_method_name {
    ($gen:tt, $gen_nbytes:tt) => {
        for_each_method_name!(@call $gen u8);
        for_each_method_name!(@call $gen i8);
        for_each_method_name!(@call $gen u16 le ne);
        for_each_method_name!(@call $gen i16 le ne);
        for_each_method_name!(@call $gen u32 le ne);
        for_each_method_name!(@call $gen i32 le ne);
        for_each_method_name!(@call $gen u64 le ne);
        for_each_method_name!(@call $gen i64 le ne);
        for_each_method_name!(@call $gen u128 le ne);
        for_each_method_name!(@call $gen i128 le ne);
        for_each_method_name!(@call_nbytes $gen_nbytes u64 uint);
        for_each_method_name!(@call_nbytes $gen_nbytes i64 int);
        for_each_method_name!(@call $gen f32 le ne);
        for_each_method_name!(@call $gen f64 le ne);

    };

    (@call $gen:tt $type:ident $($endian:ident)*) => {
        $gen!($type, $type);
        paste! {
            $($gen!($type, [<$type _ $endian>]);)*
        }
    };

    (@call_nbytes $gen_nbytes:tt $type:ident $name:ident) => {
        $gen_nbytes!($type, $name);
        paste! {
            $gen_nbytes!($type, [<$name _le>]);
            $gen_nbytes!($type, [<$name _ne>]);
        }
    };
}

macro_rules! gen_try_get {
    ($type:ident, $name:ident) => {
        paste! {
            fn [<try_get_ $name>](&mut self) -> Option<$type> {
                if self.remaining() < mem::size_of::<$type>() {
                    return None;
                }
                Some(self.[<get_ $name>]())
            }
        }
    };
}

macro_rules! gen_try_get_nbytes {
    ($type:ident, $name:ident) => {
        paste! {
            fn [<try_get_ $name>](&mut self, nbytes: usize) -> Option<$type> {
                if self.remaining() < nbytes {
                    return None;
                }
                Some(self.[<get_ $name>](nbytes))
            }
        }
    };
}

/// Extends the `Buf` trait.
///
/// It adds `try_get_X` methods that check the buffer size before reading.
pub trait BufExt: Buf {
    for_each_method_name!(gen_try_get, gen_try_get_nbytes);
}

impl<T> BufExt for T where T: Buf {}

macro_rules! gen_peek {
    ($type:ident, $name:ident) => {
        paste! {
            fn [<peek_ $name>](&self) -> Option<$type> {
                self.peek_slice(mem::size_of::<$type>()).map(|mut slice| slice.[<get_ $name>]())
            }
        }
    };
}

macro_rules! gen_peek_nbytes {
    ($type:ident, $name:ident) => {
        paste! {
            fn [<peek_ $name>](&self, nbytes: usize) -> Option<$type> {
                self.peek_slice(nbytes).map(|mut slice| slice.[<get_ $name>](nbytes))
            }
        }
    };
}

/// Provides `peek_X` methods.
///
/// We cannot implement `BufPeekExt` for `Buf` types because `Buf::chunk` only returns the current
/// chunk, which may contain less than the full buffer data.
pub trait BufPeekExt {
    for_each_method_name!(gen_peek, gen_peek_nbytes);

    fn peek_slice(&self, size: usize) -> Option<&[u8]>;

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
    fn peek_slice(&self, size: usize) -> Option<&[u8]> {
        let slice = self.as_ref();
        if slice.len() < size {
            return None;
        }
        Some(&slice[..size])
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

    fn try_get_slice<'a>(&mut self, size: usize) -> Option<&'a [u8]>
    where
        Self: 'a,
    {
        if self.remaining() < size {
            return None;
        }
        Some(self.get_slice(size))
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

    fn some(bytes: &[u8]) -> Option<&[u8]> {
        Some(bytes)
    }

    macro_rules! test_try_get_and_peek {
        ($array:expr, ($($type:ident),+), $expect:expr, $expect_le:expr $(,)?) => {
            paste! {
                $(
                    test_try_get_and_peek!($array, ($type), $expect);
                    test_try_get_and_peek!($array, ([<$type _le>]), $expect_le);
                    if cfg!(target_endian = "big") {
                        test_try_get_and_peek!($array, ([<$type _ne>]), $expect);
                    } else {
                        test_try_get_and_peek!($array, ([<$type _ne>]), $expect_le);
                    }
                )*
            }
        };

        ($array:expr, ($($type:ident),+), $expect:expr $(,)?) => {
            paste! {
                $(
                    let mut buf: &[u8] = &$array;
                    assert_eq!(buf.[<try_get_ $type>](), Some($expect));
                    assert_eq!(buf, &[]);

                    let mut buf: &[u8] = &$array[1..];
                    assert_eq!(buf.[<try_get_ $type>](), None);
                    assert_eq!(buf, &$array[1..]);

                    let buf: &[u8] = &$array;
                    assert_eq!(buf.[<peek_ $type>](), Some($expect));

                    let buf: &[u8] = &$array[1..];
                    assert_eq!(buf.[<peek_ $type>](), None);
                )*
            }
        };
    }

    #[test]
    fn try_get_and_peek() {
        test_try_get_and_peek!([1], (u8, i8), 1);
        test_try_get_and_peek!([1, 2], (u16, i16), 0x0102, 0x0201);
        test_try_get_and_peek!([1, 2, 3, 4], (u32, i32), 0x01020304, 0x04030201);
        test_try_get_and_peek!(
            [1, 2, 3, 4, 5, 6, 7, 8],
            (u64, i64),
            0x0102030405060708,
            0x0807060504030201,
        );
        test_try_get_and_peek!(
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
            (u128, i128),
            0x0102030405060708090a0b0c0d0e0f10,
            0x100f0e0d0c0b0a090807060504030201,
        );
        test_try_get_and_peek!([0, 0, 0, 0], (f32), 0f32);
        test_try_get_and_peek!([0, 0, 0, 0, 0, 0, 0, 0], (f64), 0f64);
    }

    macro_rules! test_try_get_and_peek_nbytes {
        ($type:ident) => {
            paste! {
                test_try_get_and_peek_nbytes!($type, 0x010203);
                test_try_get_and_peek_nbytes!([<$type _le>], 0x030201);
                if cfg!(target_endian = "big") {
                    test_try_get_and_peek_nbytes!([<$type _ne>], 0x010203);
                } else {
                    test_try_get_and_peek_nbytes!([<$type _ne>], 0x030201);
                }
            }
        };

        ($name:ident, $expect:expr) => {
            paste! {
                let mut buf: &[u8] = &[1, 2, 3];
                assert_eq!(buf.[<try_get_ $name>](3), Some($expect));
                assert_eq!(buf, &[]);

                let mut buf: &[u8] = &[1, 2, 3];
                assert_eq!(buf.[<try_get_ $name>](4), None);
                assert_eq!(buf, &[1, 2, 3]);

                let buf: &[u8] = &[1, 2, 3];
                assert_eq!(buf.[<peek_ $name>](3), Some($expect));

                let buf: &[u8] = &[1, 2, 3];
                assert_eq!(buf.[<peek_ $name>](4), None);
            }
        };
    }

    #[test]
    fn try_get_and_peek_nbytes() {
        test_try_get_and_peek_nbytes!(uint);
        test_try_get_and_peek_nbytes!(int);
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
        assert_eq!(buffer.peek_slice(0), some(b""));
        assert_eq!(buffer.peek_slice(1), None);
        assert_eq!(buffer.peek_slice_until(|_| true), None);
        assert_eq!(buffer.peek_slice_until(|_| false), None);
        assert_eq!(buffer.peek_slice_until_strip(|_| true), None);
        assert_eq!(buffer.peek_slice_until_strip(|_| false), None);

        let buffer = b"hello world".as_slice();
        assert_eq!(buffer.peek_slice(0), some(b""));
        assert_eq!(buffer.peek_slice(1), some(b"h"));
        assert_eq!(buffer.peek_slice(11), some(b"hello world"));
        assert_eq!(buffer.peek_slice(12), None);
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
        assert_eq!(buffer.try_get_slice(0), some(b""));
        assert_eq!(buffer.try_get_slice(1), None);

        let mut buffer = b"hello world".as_slice();
        assert_eq!(buffer.try_get_slice(5), some(b"hello"));
        assert_eq!(buffer, b" world");
        assert_eq!(buffer.try_get_slice(7), None);
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
