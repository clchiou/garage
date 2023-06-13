use std::error;
use std::fmt;

use serde::{de, ser};

/// Deserializer Dynamic Dispatch
///
/// In Rust, trait objects are the usual way to use dynamic dispatch.  However,
/// `serde::de::Deserializer` and `serde::de::Error` cannot be made into trait objects because they
/// require the `Sized` bound (for more details, check [object safety]).  To work around this
/// limitation, we offer an enum wrapper called `Either` that dynamically dispatches to either one
/// of the underlying deserializers.
///
/// `Either` has one more limitation: On each variant, `Deserializer` has three possible
/// implementations (`&Self`, `&mut Self`, and `Self).  In total there are nine combinations, and
/// we cannot implement all nine combinations for `Either` (maybe we could if we enable the generic
/// speicalization, but I doubt it is worth the effort).  Instead we offer a subset of
/// combinations, and callers have to ensure that `L` and `R` fits.
///
/// [object safety]: https://doc.rust-lang.org/reference/items/traits.html#object-safety
#[derive(Debug)]
pub enum Either<L, R> {
    Left(L),
    Right(R),
}

#[derive(Debug)]
pub enum Error<L, R>
where
    L: fmt::Debug,
    R: fmt::Debug,
{
    Custom(String),
    Left(L),
    Right(R),
}

macro_rules! forward {
    ($func_root:ident $($arg:ident)*) => {
        paste::paste! {
            crate::deserialize!($func_root(self, $($arg, )* visitor) {
                Ok(match self {
                    Either::Left(this) => {
                        this.[<deserialize_ $func_root>]($($arg, )* visitor)
                            .map_err(Error::Left)?
                    }
                    Either::Right(this) => {
                        this.[<deserialize_ $func_root>]($($arg, )* visitor)
                            .map_err(Error::Right)?
                    }
                })
            });
        }
    };
}

impl<'de, 'a, L, R> de::Deserializer<'de> for &'a Either<L, R>
where
    &'a L: de::Deserializer<'de>,
    &'a R: de::Deserializer<'de>,
{
    type Error =
        Error<<&'a L as de::Deserializer<'de>>::Error, <&'a R as de::Deserializer<'de>>::Error>;

    crate::deserialize_for_each!(forward);
}

impl<'de, 'a, L, R> de::Deserializer<'de> for &'a mut Either<L, R>
where
    &'a mut L: de::Deserializer<'de>,
    &'a mut R: de::Deserializer<'de>,
{
    type Error = Error<
        <&'a mut L as de::Deserializer<'de>>::Error,
        <&'a mut R as de::Deserializer<'de>>::Error,
    >;

    crate::deserialize_for_each!(forward);
}

impl<'de, L, R> de::Deserializer<'de> for Either<L, R>
where
    L: de::Deserializer<'de>,
    R: de::Deserializer<'de>,
{
    type Error = Error<L::Error, R::Error>;

    crate::deserialize_for_each!(forward);
}

impl<L, R> fmt::Display for Error<L, R>
where
    L: fmt::Debug + fmt::Display,
    R: fmt::Debug + fmt::Display,
{
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            Error::Custom(message) => f.write_str(message),
            Error::Left(this) => fmt::Display::fmt(this, f),
            Error::Right(this) => fmt::Display::fmt(this, f),
        }
    }
}

impl<L, R> error::Error for Error<L, R>
where
    L: fmt::Debug + fmt::Display,
    R: fmt::Debug + fmt::Display,
{
}

impl<L, R> de::Error for Error<L, R>
where
    L: fmt::Debug + fmt::Display,
    R: fmt::Debug + fmt::Display,
{
    fn custom<T: fmt::Display>(message: T) -> Self {
        Error::Custom(message.to_string())
    }
}

impl<L, R> ser::Error for Error<L, R>
where
    L: fmt::Debug + fmt::Display,
    R: fmt::Debug + fmt::Display,
{
    fn custom<T: fmt::Display>(message: T) -> Self {
        Error::Custom(message.to_string())
    }
}
