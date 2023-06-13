/// Generates a `serde::de::Deserializer` method.
///
/// NOTE: The `paste::paste!` dependency is exposed to callers.
#[macro_export]
macro_rules! deserialize {
    (unit_struct($self:ident, $name:ident, $visitor:ident $(,)?) $body:expr) => {
        $crate::__deserialize!(unit_struct($self, ($name: &'static str), $visitor) $body);
    };
    (unit_struct => $delegate:ident) => {
        ::paste::paste! {
            $crate::deserialize!(
                unit_struct(self, _name, visitor) self.[<deserialize_ $delegate>](visitor)
            );
        }
    };

    (newtype_struct($self:ident, $name:ident, $visitor:ident $(,)?) $body:expr) => {
        $crate::__deserialize!(newtype_struct($self, ($name: &'static str), $visitor) $body);
    };
    (newtype_struct => $delegate:ident) => {
        ::paste::paste! {
            $crate::deserialize!(
                newtype_struct(self, _name, visitor) self.[<deserialize_ $delegate>](visitor)
            );
        }
    };

    (tuple($self:ident, $len:ident, $visitor:ident $(,)?) $body:expr) => {
        $crate::__deserialize!(tuple($self, ($len: usize), $visitor) $body);
    };
    (tuple => $delegate:ident) => {
        ::paste::paste! {
            $crate::deserialize!(
                tuple(self, _len, visitor) self.[<deserialize_ $delegate>](visitor)
            );
        }
    };

    (tuple_struct($self:ident, $name:ident, $len:ident, $visitor:ident $(,)?) $body:expr) => {
        $crate::__deserialize!(
            tuple_struct($self, ($name: &'static str), ($len: usize), $visitor) $body
        );
    };
    (tuple_struct => $delegate:ident) => {
        ::paste::paste! {
            $crate::deserialize!(
                tuple_struct(self, _name, _len, visitor) self.[<deserialize_ $delegate>](visitor)
            );
        }
    };

    (struct($self:ident, $name:ident, $fields:ident, $visitor:ident $(,)?) $body:expr) => {
        $crate::__deserialize!(
            struct($self, ($name: &'static str), ($fields: &'static [&'static str]), $visitor) $body
        );
    };
    (struct => $delegate:ident) => {
        ::paste::paste! {
            $crate::deserialize!(
                struct(self, _name, _fields, visitor) self.[<deserialize_ $delegate>](visitor)
            );
        }
    };

    (enum($self:ident, $name:ident, $variants:ident, $visitor:ident $(,)?) $body:expr) => {
        $crate::__deserialize!(
            enum($self, ($name: &'static str), ($variants: &'static [&'static str]), $visitor) $body
        );
    };
    (enum => $delegate:ident) => {
        ::paste::paste! {
            $crate::deserialize!(
                enum(self, _name, _variants, visitor) self.[<deserialize_ $delegate>](visitor)
            );
        }
    };

    ($func_root:ident($self:ident, $visitor:ident $(,)?) $body:expr) => {
        $crate::__deserialize!($func_root($self, $visitor) $body);
    };
    ($func_root:ident => $delegate:ident) => {
        ::paste::paste! {
            $crate::deserialize!(
                $func_root(self, visitor) self.[<deserialize_ $delegate>](visitor)
            );
        }
    };
}

#[macro_export]
macro_rules! __deserialize {
    // Adds extra parentheses around the `$arg`-`$arg_type` pair to work around Rust's local
    // ambiguity limitation.
    (
        $func_root:ident($self:ident, $(($arg:ident: $arg_type:ty), )* $visitor:ident $(,)?)
        $body:expr
    ) => {
        ::paste::paste! {
            fn [<deserialize_ $func_root>]<V>(
                $self,
                $($arg: $arg_type, )*
                $visitor: V,
            ) -> ::std::result::Result<V::Value, Self::Error>
            where
                V: ::serde::de::Visitor<'de>,
            {
                $body
            }
        }
    };
}

/// Calls `$macro_func` on each `serde::de::Deserializer` method.
#[macro_export]
macro_rules! deserialize_for_each {
    ($macro_func:ident) => {
        $macro_func!(any);
        $macro_func!(bool);
        $macro_func!(i8);
        $macro_func!(i16);
        $macro_func!(i32);
        $macro_func!(i64);
        $macro_func!(u8);
        $macro_func!(u16);
        $macro_func!(u32);
        $macro_func!(u64);
        ::serde::serde_if_integer128! {
            $macro_func!(i128);
            $macro_func!(u128);
        }
        $macro_func!(f32);
        $macro_func!(f64);
        $macro_func!(char);
        $macro_func!(str);
        $macro_func!(string);
        $macro_func!(bytes);
        $macro_func!(byte_buf);
        $macro_func!(option);
        $macro_func!(unit);
        $macro_func!(unit_struct name);
        $macro_func!(newtype_struct name);
        $macro_func!(seq);
        $macro_func!(tuple len);
        $macro_func!(tuple_struct name len);
        $macro_func!(map);
        $macro_func!(struct name fields);
        $macro_func!(enum name variants);
        $macro_func!(identifier);
        $macro_func!(ignored_any);
    };
}

/// Generates a `serde::ser::Serializer` method.
///
/// NOTE: The `paste::paste!` dependency is exposed to callers.
#[macro_export]
macro_rules! serialize {
    (str($self:ident, $value:ident $(,)?) $body:expr) => {
        $crate::__serialize!(str($self, $value: &str) $body);
    };

    (bytes($self:ident, $value:ident $(,)?) $body:expr) => {
        $crate::__serialize!(bytes($self, $value: &[u8]) $body);
    };

    (none($self:ident) $body:expr $(,)?) => {
        $crate::__serialize!(none($self) $body);
    };
    (some($self:ident, $value:ident $(,)?) $body:expr) => {
        $crate::__serialize!(some<T>($self, $value: &T) $body);
    };

    (unit($self:ident $(,)?) $body:expr) => {
        $crate::__serialize!(unit($self) $body);
    };

    (unit_struct($self:ident, $name:ident $(,)?) $body:expr) => {
        $crate::__serialize!(unit_struct($self, $name: &'static str) $body);
    };

    (
        unit_variant($self:ident, $name:ident, $variant_index:ident, $variant:ident $(,)?)
        $body:expr
    ) => {
        $crate::__serialize!(
            unit_variant($self, $name: &'static str, $variant_index: u32, $variant: &'static str)
            $body
        );
    };

    (newtype_struct($self:ident, $name:ident, $value:ident $(,)?) $body:expr) => {
        $crate::__serialize!(newtype_struct<T>($self, $name: &'static str, $value: &T) $body);
    };

    (
        newtype_variant(
            $self:ident,
            $name:ident,
            $variant_index:ident,
            $variant:ident,
            $value:ident $(,)?
        )
        $body:expr
    ) => {
        $crate::__serialize!(
            newtype_variant<T>(
                $self,
                $name: &'static str,
                $variant_index: u32,
                $variant: &'static str,
                $value: &T,
            )
            $body
        );
    };

    (seq($self:ident, $len:ident $(,)?) $body:expr) => {
        $crate::__serialize!(seq($self, $len: Option<usize>) -> Self::SerializeSeq { $body });
    };

    (tuple($self:ident, $len:ident $(,)?) $body:expr) => {
        $crate::__serialize!(tuple($self, $len: usize) -> Self::SerializeSeq { $body });
    };

    (tuple_struct($self:ident, $name:ident, $len:ident $(,)?) $body:expr) => {
        $crate::__serialize!(
            tuple_struct($self, $name: &'static str, $len: usize) -> Self::SerializeTupleStruct {
                $body
            }
        );
    };

    (
        tuple_variant(
            $self:ident,
            $name:ident,
            $variant_index:ident,
            $variant:ident,
            $len:ident $(,)?
        )
        $body:expr
    ) => {
        $crate::__serialize!(
            tuple_variant(
                $self,
                $name: &'static str,
                $variant_index: u32,
                $variant: &'static str,
                $len: usize,
            ) -> Self::SerializeTupleVariant {
                $body
            }
        );
    };

    (map($self:ident, $len:ident $(,)?) $body:expr) => {
        $crate::__serialize!(map($self, $len: Option<usize>) -> Self::SerializeMap { $body });
    };

    (struct($self:ident, $name:ident, $len:ident $(,)?) $body:expr) => {
        $crate::__serialize!(
            struct($self, $name: &'static str, $len: usize) -> Self::SerializeStruct { $body }
        );
    };

    (
        struct_variant(
            $self:ident,
            $name:ident,
            $variant_index:ident,
            $variant:ident,
            $len:ident $(,)?
        )
        $body:expr
    ) => {
        $crate::__serialize!(
            struct_variant(
                $self,
                $name: &'static str,
                $variant_index: u32,
                $variant: &'static str,
                $len: usize,
            ) -> Self::SerializeStructVariant {
                $body
            }
        );
    };

    ($func_root:ident($self:ident, $value:ident $(,)?) $body:expr) => {
        $crate::__serialize!($func_root($self, $value: $func_root) $body);
    };
}

#[macro_export]
macro_rules! __serialize {
    (
        $func_root:ident$(<$t:ident>)?($self:ident $(, $arg:ident: $arg_type:ty)* $(,)?)
        $body:expr
    ) => {
        $crate::__serialize!($func_root$(<$t>)*($self $(, $arg: $arg_type)*) -> Self::Ok {
            $body
        });
    };

    // `$ret` is captured as `ty`, not `ident`, because Rust's macro parser cannot correctly
    // distinguish between `-> $ret:ident $body:expr` and `$body:expr` (the reasons are still
    // unclear to me).  Additionally, extra curly brackets are added around `$body` because Rust
    // does not allow `ty` to be followed by `expr`.
    (
        $func_root:ident$(<$t:ident>)?($self:ident $(, $arg:ident: $arg_type:ty)* $(,)?)
        -> $ret:ty { $body:expr }
    ) => {
        ::paste::paste! {
            fn [<serialize_ $func_root>]$(<$t>)*(
                $self
                $(, $arg: $arg_type)*
            ) -> ::std::result::Result<$ret, Self::Error>
            $(
            where
                $t: ::serde::Serialize + ?::std::marker::Sized,
            )*
            {
                $body
            }
        }
    };
}
