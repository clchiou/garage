mod de;
mod de_impl;
mod ser_impl;

//
// TODO: At the moment, we have chosen not to implement a serializer for YAML-to-Bencode
// serialization (which is required to serialize tagged nodes).
// ```
// mod ser;
// ```
//
// In `serde_yaml`, when serializing a tagged node, the `Serialize` implementor produces a
// single-entry map in the form `!tag: value` [1], and `Serializer` implementors are expected to
// detect this single-entry map.  This tacit agreement between `Serialize` and `Serializer`
// implementors feels awkward, and I would prefer not to re-implement it here.
//
// [1]: https://github.com/dtolnay/serde-yaml/blob/master/src/value/tagged.rs#L190
//

/// Adapter that converts byte strings to UTF-8 strings right before sending them to `serde_yaml`.
///
/// It is required for to-YAML conversions:
/// ```
/// # use serde::de::Deserialize;
/// # use bt_bencode::{Value, Yaml};
/// # let bencode = Value::Integer(0);
/// # let yaml = serde_yaml::Value::Number(0i64.into());
/// assert_eq!(serde_yaml::to_value(&Yaml(&bencode)).unwrap(), yaml);
/// assert_eq!(serde_yaml::Value::deserialize(Yaml(bencode)).unwrap(), yaml);
/// ```
/// ...And for from-YAML conversions when the input contains tagged nodes:
/// ```
/// # use bt_bencode::{Value, Yaml};
/// # let bencode = Value::Integer(0);
/// # let yaml = serde_yaml::Value::Number(0i64.into());
/// assert_eq!(serde_yaml::from_value::<Yaml<Value>>(yaml).unwrap(), Yaml(bencode));
/// ```
///
/// When a byte string is not UTF-8 encoded, it produces a tagged string.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Yaml<V>(pub V);

const BYTES_TAG: &str = "bytes";

#[cfg(test)]
mod tests {
    use bytes::Bytes;
    use serde::ser::Error as _;

    use crate::error::Error;
    use crate::testing::{BENCODE, EXTENDED_BENCODE, REDUCED_YAML, TAG_YAML, YAML};

    #[test]
    fn to_bencode() {
        assert_eq!(
            crate::to_value(&*YAML),
            Ok(EXTENDED_BENCODE.to_own::<Bytes>()),
        );

        // We need a specialized serializer to correctly process tagged nodes (which we have chosen
        // not to implement at the moment).
        assert_eq!(
            crate::to_value::<_, Bytes>(&*TAG_YAML),
            Err(Error::custom(
                "expect byte string dictionary key: Dictionary({\"!bytes\": ByteString(\"\\\\x80\")})",
            )),
        );
        // TODO: Note that it is `ne`, not `eq`.  This feels like a time bomb, as `to_value(yaml)`
        // can sometimes silently produce incorrect results.
        assert_ne!(
            crate::to_value(&*REDUCED_YAML),
            Ok(BENCODE.to_own::<Bytes>()),
        );
    }
}
