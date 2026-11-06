use serde_json::value::{Index, Value};

pub trait ValueExt {
    fn as_intlike(&self) -> Option<i64>;

    fn as_slice(&self) -> Option<&[Value]>;

    //
    // `as_slice_or_null` returns an empty slice for `null`, whereas `as_str_or_null` returns an
    // `Option<&str>`.  I am not sure if this is a good idea, but I think it makes more sense,
    // despite being slightly inconsistent.
    //

    fn as_slice_or_null(&self) -> Option<&[Value]>;

    fn as_str_or_null(&self) -> Option<Option<&str>>;

    // This does not allocate intermediate `String`s, unlike `Value::pointer`.
    fn get_by_path<const N: usize>(&self, path: [&dyn Index; N]) -> Option<&Value>;
}

impl ValueExt for Value {
    fn as_intlike(&self) -> Option<i64> {
        match self {
            Value::Number(number) => number.as_i64(),
            Value::String(string) => string.parse().ok(),
            _ => None,
        }
    }

    fn as_slice(&self) -> Option<&[Value]> {
        match self {
            Value::Array(array) => Some(array),
            _ => None,
        }
    }

    fn as_slice_or_null(&self) -> Option<&[Value]> {
        match self {
            Value::Array(array) => Some(array),
            Value::Null => Some(&[]),
            _ => None,
        }
    }

    fn as_str_or_null(&self) -> Option<Option<&str>> {
        match self {
            Value::String(string) => Some(Some(string.as_str())),
            Value::Null => Some(None),
            _ => None,
        }
    }

    fn get_by_path<const N: usize>(&self, path: [&dyn Index; N]) -> Option<&Value> {
        path.into_iter().try_fold(self, |value, key| value.get(key))
    }
}
