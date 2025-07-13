use bt_bencode::own::bytes::{ByteString, Value};

pub(crate) fn reinsert<T>(extra: &mut Value, key: &'static [u8], value: Option<T>)
where
    // NOTE: We should not use `T: Serialize` because the `bt_base` types, such as `NodeId`,
    // implement their own `Serialize`, which differs from ours.
    T: ToValue,
{
    if let Some(value) = value {
        extra
            .as_dictionary_mut()
            .expect("dictionary")
            .insert(ByteString::from_static(key), value.to_value());
    }
}

pub(crate) trait ToValue {
    fn to_value(self) -> Value;
}

impl ToValue for ByteString {
    fn to_value(self) -> Value {
        Value::ByteString(self)
    }
}

impl ToValue for bool {
    fn to_value(self) -> Value {
        Value::Integer(self.into())
    }
}

impl ToValue for u16 {
    fn to_value(self) -> Value {
        Value::Integer(self.into())
    }
}
