//! Extends the `bytes` crate.

use std::mem;

use bytes::Buf;
use paste::paste;

pub use g1_bytes_derive::{BufExt, BufMutExt};

macro_rules! def_try_get {
    ($type:ident $($endian:ident)*) => {
        def_try_get!(@ $type $type);
        paste! {
            $(
                def_try_get!(@ $type [<$type _ $endian>]);
            )*
        }
    };

    (@ $type:ident $name:ident) => {
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

macro_rules! def_try_get_n {
    ($type:ident $name:ident) => {
        def_try_get_n!(@ $type $name);
        paste! {
            def_try_get_n!(@ $type [<$name _le>]);
            def_try_get_n!(@ $type [<$name _ne>]);
        }
    };

    (@ $type:ident $name:ident) => {
        paste! {
            fn [<try_get_ $name>](&mut self, nbytes: usize) -> Option<$type> {
                if self.remaining() < nbytes {
                    return None;
                }
                Some(self.[<get_ $name>](nbytes))
            }
        }
    }
}

/// Extends the `Buf` trait.
///
/// It adds `try_get_X` methods that check the buffer size before reading.
pub trait BufExt: Buf {
    def_try_get!(u8);
    def_try_get!(i8);
    def_try_get!(u16 le ne);
    def_try_get!(i16 le ne);
    def_try_get!(u32 le ne);
    def_try_get!(i32 le ne);
    def_try_get!(u64 le ne);
    def_try_get!(i64 le ne);
    def_try_get!(u128 le ne);
    def_try_get!(i128 le ne);
    def_try_get_n!(u64 uint);
    def_try_get_n!(i64 int);
    def_try_get!(f32 le ne);
    def_try_get!(f64 le ne);
}

impl<T> BufExt for T where T: Buf {}

#[cfg(test)]
mod tests {
    use super::*;

    macro_rules! test_try_get {
        ($array:expr, ($($type:ident),+), $expect:expr, $expect_le:expr $(,)?) => {
            paste! {
                $(
                    test_try_get!($array, ($type), $expect);
                    test_try_get!($array, ([<$type _le>]), $expect_le);
                    if cfg!(target_endian = "big") {
                        test_try_get!($array, ([<$type _ne>]), $expect);
                    } else {
                        test_try_get!($array, ([<$type _ne>]), $expect_le);
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
                )*
            }
        };
    }

    #[test]
    fn try_get() {
        test_try_get!([1], (u8, i8), 1);
        test_try_get!([1, 2], (u16, i16), 0x0102, 0x0201);
        test_try_get!([1, 2, 3, 4], (u32, i32), 0x01020304, 0x04030201);
        test_try_get!(
            [1, 2, 3, 4, 5, 6, 7, 8],
            (u64, i64),
            0x0102030405060708,
            0x0807060504030201,
        );
        test_try_get!(
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
            (u128, i128),
            0x0102030405060708090a0b0c0d0e0f10,
            0x100f0e0d0c0b0a090807060504030201,
        );
        test_try_get!([0, 0, 0, 0], (f32), 0f32);
        test_try_get!([0, 0, 0, 0, 0, 0, 0, 0], (f64), 0f64);
    }

    macro_rules! test_try_get_nbytes {
        () => {
            test_try_get_nbytes!(uint);
            test_try_get_nbytes!(int);
        };

        ($type:ident) => {
            paste! {
                test_try_get_nbytes!([<try_get_ $type>], 0x010203);
                test_try_get_nbytes!([<try_get_ $type _le>], 0x030201);
                if cfg!(target_endian = "big") {
                    test_try_get_nbytes!([<try_get_ $type _ne>], 0x010203);
                } else {
                    test_try_get_nbytes!([<try_get_ $type _ne>], 0x030201);
                }
            }
        };

        ($method:ident, $expect:expr) => {
            let mut buf: &[u8] = &[1, 2, 3];
            assert_eq!(buf.$method(3), Some($expect));
            assert_eq!(buf, &[]);

            let mut buf: &[u8] = &[1, 2, 3];
            assert_eq!(buf.$method(4), None);
            assert_eq!(buf, &[1, 2, 3]);
        };
    }

    #[test]
    fn try_get_nbytes() {
        test_try_get_nbytes!();
    }

    #[derive(BufExt, BufMutExt, Debug, Eq, PartialEq)]
    #[endian("little")]
    struct Struct {
        x: u16,
        #[endian("big")]
        y: u16,
    }

    #[derive(BufExt, BufMutExt, Debug, Eq, PartialEq)]
    struct Tuple(u16, #[endian("little")] u32);

    #[derive(BufExt, BufMutExt, Debug, Eq, PartialEq)]
    struct Unit;

    #[test]
    fn buf_ext() {
        let x = Struct {
            x: 0x0201,
            y: 0x0304,
        };
        let mut buf: &[u8] = &[1, 2, 3, 4];
        assert_eq!(buf.get_struct(), x);
        assert_eq!(buf, &[]);
        let mut buf: &[u8] = &[1, 2, 3, 4];
        assert_eq!(buf.try_get_struct(), Some(x));
        assert_eq!(buf, &[]);
        let mut buf: &[u8] = &[0; 3];
        assert_eq!(buf.try_get_struct(), None);
        assert_eq!(buf, &[0; 3]);

        let x = Tuple(0x0102, 0x06050403);
        let mut buf: &[u8] = &[1, 2, 3, 4, 5, 6];
        assert_eq!(buf.get_tuple(), x);
        assert_eq!(buf, &[]);
        let mut buf: &[u8] = &[1, 2, 3, 4, 5, 6];
        assert_eq!(buf.try_get_tuple(), Some(x));
        assert_eq!(buf, &[]);
        let mut buf: &[u8] = &[0; 5];
        assert_eq!(buf.try_get_tuple(), None);
        assert_eq!(buf, &[0; 5]);

        let mut buf: &[u8] = &[];
        assert_eq!(buf.get_unit(), Unit);
        assert_eq!(buf, &[]);
        assert_eq!(buf.try_get_unit(), Some(Unit));
        assert_eq!(buf, &[]);
    }

    #[test]
    fn buf_mut_ext() {
        let mut buf = Vec::new();
        buf.put_struct(&Struct {
            x: 0x0201,
            y: 0x0304,
        });
        assert_eq!(buf, [1, 2, 3, 4]);

        let mut buf = Vec::new();
        buf.put_tuple(&Tuple(0x0102, 0x06050403));
        assert_eq!(buf, [1, 2, 3, 4, 5, 6]);

        let mut buf = Vec::new();
        buf.put_unit(&Unit);
        assert_eq!(buf, []);
    }
}
