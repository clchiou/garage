mod de;
mod ser_impl;

//
// TODO: Escaping binary data makes it difficult to convert the result back to Bencode.  How can
// we represent binary data in JSON that is also convertible?
//

/// Adapter that converts byte strings to UTF-8 strings right before sending them to `serde_json`.
///
/// It is only required for to-JSON conversions:
/// ```
/// # use serde::de::Deserialize;
/// # use bt_bencode::{Json, Value};
/// # let bencode = Value::Integer(0);
/// # let json = serde_json::json!(0);
/// assert_eq!(serde_json::to_value(&Json(&bencode)).unwrap(), json);
/// assert_eq!(serde_json::Value::deserialize(Json(bencode)).unwrap(), json);
/// ```
///
/// Note that when a byte string is not UTF-8 encoded, it produces an escaped string instead of
/// returning an error.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Json<V>(pub V);

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use bytes::Bytes;
    use serde::de::Deserialize;

    use crate::testing::{EXTENDED_BENCODE, JSON};
    use crate::value::Value;

    #[test]
    fn from_json() {
        assert_eq!(
            <Value<&[u8]>>::deserialize(&*JSON).unwrap(),
            *EXTENDED_BENCODE,
        );
        assert_matches!(
            <Value<&[u8]>>::deserialize(serde_json::json!("foo bar")),
            Err(error)
            if error.to_string() == "borrow from owned byte string: b\"foo bar\"",
        );
        assert_eq!(
            serde_json::from_value::<Value<Bytes>>(JSON.clone()).unwrap(),
            EXTENDED_BENCODE.to_own(),
        );

        // Unlike with `serde_yaml`, no adapter is required here.
        let testdata = serde_json::to_string(&*JSON).unwrap();
        assert_eq!(
            serde_json::from_str::<Value<&[u8]>>(&testdata).unwrap(),
            *EXTENDED_BENCODE,
        );
        assert_eq!(
            serde_json::from_str::<Value<Bytes>>(&testdata).unwrap(),
            EXTENDED_BENCODE.to_own(),
        );
    }

    #[test]
    fn to_bencode() {
        assert_eq!(
            crate::to_value(&*JSON),
            Ok(EXTENDED_BENCODE.to_own::<Bytes>()),
        );
    }
}
