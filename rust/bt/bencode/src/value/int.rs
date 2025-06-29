use std::any;
use std::fmt;

use serde::{de, ser};

use crate::int::Int;

use super::Integer;

pub(super) trait FromInt: Int {
    fn de_from_int<I, E>(value: I) -> Result<Self, E>
    where
        I: Int + TryInto<Self>,
        E: de::Error;

    fn ser_from_int<I, E>(value: I) -> Result<Self, E>
    where
        I: Int + TryInto<Self>,
        E: ser::Error;
}

impl FromInt for Integer {
    fn de_from_int<I, E>(value: I) -> Result<Self, E>
    where
        I: Int + TryInto<Self>,
        E: de::Error,
    {
        from_int(value).map_err(E::custom)
    }

    fn ser_from_int<I, E>(value: I) -> Result<Self, E>
    where
        I: Int + TryInto<Self>,
        E: ser::Error,
    {
        from_int(value).map_err(E::custom)
    }
}

// We choose `impl fmt::Display` as the error type because Rust does not support
// `E: de::Error | ser::Error`.
fn from_int<I>(value: I) -> Result<Integer, impl fmt::Display>
where
    I: Int + TryInto<Integer>,
{
    value.try_into().map_err(|_| {
        fmt::from_fn(move |f| {
            std::write!(
                f,
                "{}-to-{} overflow: {}",
                any::type_name::<I>(),
                any::type_name::<Integer>(),
                value,
            )
        })
    })
}
