use serde::de::Deserializer;
use serde::ser::Serializer;
use serde::{Deserialize, Serialize};

use bt_serde::SerdeWith;

#[test]
fn optional() {
    #[bt_serde::optional]
    #[derive(Debug, Deserialize, PartialEq, Serialize)]
    struct Struct {
        x: Option<String>,
        #[optional(with = "MyString")]
        y: Option<MyString>,
    }

    #[derive(Debug, PartialEq)]
    struct MyString(String);

    impl SerdeWith for MyString {
        type Value = Self;

        fn deserialize<'de, D>(deserializer: D) -> Result<Self::Value, D::Error>
        where
            D: Deserializer<'de>,
        {
            String::deserialize(deserializer).map(Self)
        }

        fn serialize<S>(value: &Self::Value, serializer: S) -> Result<S::Ok, S::Error>
        where
            S: Serializer,
        {
            value.0.serialize(serializer)
        }
    }

    for (value, json) in [
        (
            Struct {
                x: Some("foo".into()),
                y: Some(MyString("bar".into())),
            },
            r#"{"x":"foo","y":"bar"}"#,
        ),
        (Struct { x: None, y: None }, "{}"),
    ] {
        assert_eq!(serde_json::to_string(&value).unwrap(), json);
        assert_eq!(serde_json::from_str::<Struct>(json).unwrap(), value);
    }
}
