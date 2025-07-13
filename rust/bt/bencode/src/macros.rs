// TODO: Return `Value<B>` for all `B: OwnedBStr`, and even for `&[u8]`.
#[macro_export]
macro_rules! bencode {
    ([ $($i:tt)* ]) => { $crate::_b!(@l []       [ $($i)* ]) };
    ({ $($i:tt)* }) => { $crate::_b!(@d [] [] [] [ $($i)* ]) };
    (  $i:expr    ) => { $crate::_b!(@v            $i      ) };
}

#[macro_export]
macro_rules! _b {
    (@v $v:expr) => {
        $crate::macros::ToValue::to_value($v)
    };

    (@l [ $($o:expr,)* ] []) => {
        $crate::Value::List([$($o),*].into())
    };

    (@d [ $($o:expr,)* ] [] [] []) => {
        $crate::Value::Dictionary([$($o),*].into())
    };

    (@k $k:expr) => {
        $crate::macros::ToKey::to_key($k)
    };

    //
    // List
    //

    (@l [ $($o:expr,)* ] [          [ $($e:tt)* ],      $($i:tt)* ]) => { $crate::_b!
    (@l [ $($o,)* $crate::_b!(@l [] [ $($e)*    ]), ] [ $($i)*    ]) };

    (@l [ $($o:expr,)* ] [          [ $($e:tt)* ]                 ]) => { $crate::_b!
    (@l [ $($o,)* $crate::_b!(@l [] [ $($e)*    ]), ] [           ]) };

    (@l [ $($o:expr,)* ] [                { $($e:tt)* },      $($i:tt)* ]) => { $crate::_b!
    (@l [ $($o,)* $crate::_b!(@d [] [] [] [ $($e)*    ]), ] [ $($i)*    ]) };

    (@l [ $($o:expr,)* ] [                { $($e:tt)* }                 ]) => { $crate::_b!
    (@l [ $($o,)* $crate::_b!(@d [] [] [] [ $($e)*    ]), ] [           ]) };

    (@l [ $($o:expr,)* ] [       $e:expr, $($i:tt)* ]) => { $crate::_b!
    (@l [ $($o,)* $crate::_b!(@v $e), ] [ $($i)*    ]) };

    (@l [ $($o:expr,)* ] [       $e:expr            ]) => { $crate::_b!
    (@l [ $($o,)* $crate::_b!(@v $e), ] [           ]) };

    //
    // Dictionary Key
    //

    (@d [ $($o:expr,)* ] [] [             $($k:tt)+    ] [ :       $($i:tt)* ]) => { $crate::_b!
    (@d [ $($o,)*      ] [ $crate::_b!(@k $($k)+)   ] [] [         $($i)*    ]) };

    (@d [ $($o:expr,)* ] [] [             $($k:tt)*    ] [ $kk:tt  $($i:tt)* ]) => { $crate::_b!
    (@d [ $($o,)*      ] [] [             $($k)*           $kk ] [ $($i)*    ]) };

    //
    // Dictionary Value
    //

    (@d [ $($o:expr,)* ] [ $k:expr ] [] [        [ $($v:tt)* ],             $($i:tt)* ]) => { $crate::_b!
    (@d [ $($o,)*         ($k, $crate::_b!(@l [] [ $($v)*    ])), ] [] [] [ $($i)*    ]) };

    (@d [ $($o:expr,)* ] [ $k:expr ] [] [        [ $($v:tt)* ]                        ]) => { $crate::_b!
    (@d [ $($o,)*         ($k, $crate::_b!(@l [] [ $($v)*    ])), ] [] [] [           ]) };

    (@d [ $($o:expr,)* ] [ $k:expr ] [] [              { $($v:tt)* },             $($i:tt)* ]) => { $crate::_b!
    (@d [ $($o,)*         ($k, $crate::_b!(@d [] [] [] [ $($v)*    ])), ] [] [] [ $($i)*    ]) };

    (@d [ $($o:expr,)* ] [ $k:expr ] [] [              { $($v:tt)* }                        ]) => { $crate::_b!
    (@d [ $($o,)*         ($k, $crate::_b!(@d [] [] [] [ $($v)*    ])), ] [] [] [           ]) };

    (@d [ $($o:expr,)* ] [ $k:expr ] [] [     $v:expr,        $($i:tt)* ]) => { $crate::_b!
    (@d [ $($o,)*         ($k, $crate::_b!(@v $v)), ] [] [] [ $($i)*    ]) };

    (@d [ $($o:expr,)* ] [ $k:expr ] [] [     $v:expr                   ]) => { $crate::_b!
    (@d [ $($o,)*         ($k, $crate::_b!(@v $v)), ] [] [] [           ]) };
}

use bytes::BytesMut;

use crate::own::bytes::{ByteString, Integer, Value};

//
// We use these traits to convert `T` to `Value` or `ByteString` instead of using `to_value`.  The
// main advantage of them is that they treat byte strings as byte strings, rather than as lists of
// bytes (which is the default behavior of Serde, and by extension, `to_value`).
//

pub trait ToValue {
    fn to_value(self) -> Value;
}

pub trait ToKey {
    fn to_key(self) -> ByteString;
}

impl ToValue for &[u8] {
    fn to_value(self) -> Value {
        Value::ByteString(ByteString::copy_from_slice(self))
    }
}

impl<const N: usize> ToValue for &[u8; N] {
    fn to_value(self) -> Value {
        Value::ByteString(ByteString::copy_from_slice(self))
    }
}

impl<const N: usize> ToValue for [u8; N] {
    fn to_value(self) -> Value {
        Value::ByteString(ByteString::copy_from_slice(&self))
    }
}

impl ToValue for Vec<u8> {
    fn to_value(self) -> Value {
        Value::ByteString(self.into())
    }
}

impl ToValue for BytesMut {
    fn to_value(self) -> Value {
        Value::ByteString(self.into())
    }
}

impl ToValue for ByteString {
    fn to_value(self) -> Value {
        Value::ByteString(self)
    }
}

impl ToValue for Integer {
    fn to_value(self) -> Value {
        Value::Integer(self)
    }
}

impl ToValue for Value {
    fn to_value(self) -> Value {
        self
    }
}

impl ToKey for &[u8] {
    fn to_key(self) -> ByteString {
        ByteString::copy_from_slice(self)
    }
}

impl<const N: usize> ToKey for &[u8; N] {
    fn to_key(self) -> ByteString {
        ByteString::copy_from_slice(self)
    }
}

impl<const N: usize> ToKey for [u8; N] {
    fn to_key(self) -> ByteString {
        ByteString::copy_from_slice(&self)
    }
}

impl ToKey for Vec<u8> {
    fn to_key(self) -> ByteString {
        self.into()
    }
}

impl ToKey for BytesMut {
    fn to_key(self) -> ByteString {
        self.into()
    }
}

impl ToKey for ByteString {
    fn to_key(self) -> ByteString {
        self
    }
}

#[cfg(test)]
mod tests {
    use bytes::Bytes;

    use crate::testing::{vb, vd, vi, vl};
    use crate::value::Value;

    #[test]
    fn test_bencode() {
        fn test(actual: Value<Bytes>, expect: Value<&[u8]>) {
            assert_eq!(actual, expect.to_own());
        }

        test(bencode!(b"hello world"), vb(b"hello world"));
        test(bencode!(*b"hello world"), vb(b"hello world"));
        test(bencode!(b"hello world".as_slice()), vb(b"hello world"));
        test(bencode!(b"hello world".to_vec()), vb(b"hello world"));

        test(bencode!(1), vi(1));

        test(bencode!([]), vl([]));
        test(bencode!([1]), vl([vi(1)]));
        test(bencode!([2, b"foo"]), vl([vi(2), vb(b"foo")]));
        // Trailing comma.
        test(bencode!([b"bar",]), vl([vb(b"bar")]));
        test(bencode!([[],]), vl([vl([])]));
        test(bencode!([{},]), vl([vd([])]));

        test(bencode!({}), vd([]));
        test(bencode!({b"w": 1}), vd([(b"w", vi(1))]));
        test(
            bencode!({b"x": 2, b"y": b"foo"}),
            vd([(b"x", vi(2)), (b"y", vb(b"foo"))]),
        );
        // Trailing comma.
        test(bencode!({b"z": b"bar", }), vd([(b"z", vb(b"bar"))]));
        test(bencode!({b"z": [], }), vd([(b"z", vl([]))]));
        test(bencode!({b"z": {}, }), vd([(b"z", vd([]))]));

        // Expression.
        let b = Bytes::from_static(b"spam");
        test(bencode!([b.clone(), 1 + 2]), vl([vb(b"spam"), vi(3)]));
        test(bencode!({b.clone(): 1 + 2}), vd([(b"spam", vi(3))]));

        // Nested.
        test(
            bencode!([{b"a": [{b"b": b"c"}]}]),
            vl([vd([(b"a", vl([vd([(b"b", vb(b"c"))])]))])]),
        );
    }
}
