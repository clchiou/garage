use std::marker::PhantomData;
use std::sync::LazyLock;

use bytes::Bytes;
use serde::de;
use serde::{Deserialize, Serialize};

use crate::raw::WithRaw;
use crate::value::{Integer, Value};

pub(crate) fn vb(bytes: &[u8]) -> Value<&[u8]> {
    Value::ByteString(bytes)
}

pub(crate) fn vi(integer: Integer) -> Value<&'static [u8]> {
    Value::Integer(integer)
}

pub(crate) fn vl<const N: usize>(items: [Value<&[u8]>; N]) -> Value<&[u8]> {
    Value::List(items.into())
}

pub(crate) fn vd<'a, const N: usize>(items: [(&'a [u8], Value<&'a [u8]>); N]) -> Value<&'a [u8]> {
    Value::Dictionary(items.into())
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub(crate) struct Unit;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub(crate) struct Newtype(pub(crate) String);

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub(crate) struct Tuple(pub(crate) u8, pub(crate) String);

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub(crate) struct Struct {
    // Ensure that the field names are unordered.
    pub(crate) a: u8,
    pub(crate) c: u8,
    pub(crate) b: u8,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub(crate) enum Enum {
    Unit,
    Newtype(String),
    Tuple(u8, String),
    Struct {
        // Ensure that the field names are unordered.
        a: u8,
        c: u8,
        b: u8,
    },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "t")]
pub(crate) enum InternallyTagged {
    Bool { value: bool },
    Char { value: char },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "t", content = "c")]
pub(crate) enum AdjacentlyTagged {
    Bool { value: bool },
    Char { value: char },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(untagged)]
pub(crate) enum Untagged {
    Bool { value: bool },
    Char { value: char },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct StrictStruct {
    pub(crate) x: u8,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) enum StrictEnum {
    Struct { x: u8 },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub(crate) struct Ignored {
    pub(crate) x: u8,
    #[serde(skip)]
    pub(crate) ignored: u8,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub(crate) struct Flatten {
    pub(crate) a: u8,
    pub(crate) c: u8,
    pub(crate) b: u8,
    #[serde(flatten)]
    pub(crate) rest: Value<Bytes>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub(crate) struct NestedA {
    pub(crate) a: String,
    pub(crate) nested: WithRaw<NestedB, Bytes>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub(crate) struct NestedB {
    pub(crate) b: String,
    pub(crate) nested: WithRaw<NestedC, Bytes>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub(crate) struct NestedC {
    pub(crate) c: String,
    pub(crate) nested: WithRaw<String, Bytes>,
}

pub(crate) struct ByteBufDeserializer<E>(Vec<u8>, PhantomData<E>);

impl<E> ByteBufDeserializer<E> {
    pub(crate) fn new(bytes: Vec<u8>) -> Self {
        Self(bytes, PhantomData)
    }
}

impl<'de, E> de::Deserializer<'de> for ByteBufDeserializer<E>
where
    E: de::Error,
{
    type Error = E;

    fn deserialize_any<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: de::Visitor<'de>,
    {
        visitor.visit_byte_buf(self.0)
    }

    serde::forward_to_deserialize_any! {
        bool
        i8 i16 i32 i64 i128
        u8 u16 u32 u64 u128
        f32 f64
        char str string
        bytes byte_buf
        option
        unit unit_struct
        newtype_struct
        seq tuple tuple_struct
        map struct
        enum
        identifier
        ignored_any
    }
}

impl<'de, E> de::IntoDeserializer<'de, E> for ByteBufDeserializer<E>
where
    E: de::Error,
{
    type Deserializer = Self;

    fn into_deserializer(self) -> Self::Deserializer {
        self
    }
}

pub(crate) struct OptionDeserializer<T, E>(Option<T>, PhantomData<E>);

impl<T, E> OptionDeserializer<T, E> {
    pub(crate) fn new(option: Option<T>) -> Self {
        Self(option, PhantomData)
    }
}

impl<'de, T, E> de::Deserializer<'de> for OptionDeserializer<T, E>
where
    T: de::IntoDeserializer<'de, E>,
    E: de::Error,
{
    type Error = E;

    fn deserialize_any<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: de::Visitor<'de>,
    {
        match self.0 {
            Some(value) => visitor.visit_some(value.into_deserializer()),
            None => visitor.visit_none(),
        }
    }

    serde::forward_to_deserialize_any! {
        bool
        i8 i16 i32 i64 i128
        u8 u16 u32 u64 u128
        f32 f64
        char str string
        bytes byte_buf
        option
        unit unit_struct
        newtype_struct
        seq tuple tuple_struct
        map struct
        enum
        identifier
        ignored_any
    }
}

impl<'de, T, E> de::IntoDeserializer<'de, E> for OptionDeserializer<T, E>
where
    T: de::IntoDeserializer<'de, E>,
    E: de::Error,
{
    type Deserializer = Self;

    fn into_deserializer(self) -> Self::Deserializer {
        self
    }
}

pub(crate) struct NewtypeStructDeserializer<T, E>(T, PhantomData<E>);

impl<T, E> NewtypeStructDeserializer<T, E> {
    pub(crate) fn new(value: T) -> Self {
        Self(value, PhantomData)
    }
}

impl<'de, T, E> de::Deserializer<'de> for NewtypeStructDeserializer<T, E>
where
    T: de::IntoDeserializer<'de, E>,
    E: de::Error,
{
    type Error = E;

    fn deserialize_any<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: de::Visitor<'de>,
    {
        visitor.visit_newtype_struct(self.0.into_deserializer())
    }

    serde::forward_to_deserialize_any! {
        bool
        i8 i16 i32 i64 i128
        u8 u16 u32 u64 u128
        f32 f64
        char str string
        bytes byte_buf
        option
        unit unit_struct
        newtype_struct
        seq tuple tuple_struct
        map struct
        enum
        identifier
        ignored_any
    }
}

impl<'de, T, E> de::IntoDeserializer<'de, E> for NewtypeStructDeserializer<T, E>
where
    T: de::IntoDeserializer<'de, E>,
    E: de::Error,
{
    type Deserializer = Self;

    fn into_deserializer(self) -> Self::Deserializer {
        self
    }
}

// Mock `EnumAccess` for `Enum::Unit`.
pub(crate) struct UnitEnumAccess<E>(PhantomData<E>);

impl<E> UnitEnumAccess<E> {
    pub(crate) fn new() -> Self {
        Self(PhantomData)
    }
}

impl<'de, E> de::EnumAccess<'de> for UnitEnumAccess<E>
where
    E: de::Error,
{
    type Error = E;
    type Variant = Self;

    fn variant_seed<V>(self, seed: V) -> Result<(V::Value, Self::Variant), Self::Error>
    where
        V: de::DeserializeSeed<'de>,
    {
        Ok((
            seed.deserialize(de::value::BorrowedStrDeserializer::new("Unit"))?,
            self,
        ))
    }
}

impl<'de, E> de::VariantAccess<'de> for UnitEnumAccess<E>
where
    E: de::Error,
{
    type Error = E;

    fn unit_variant(self) -> Result<(), Self::Error> {
        Ok(())
    }

    fn newtype_variant_seed<T>(self, _seed: T) -> Result<T::Value, Self::Error>
    where
        T: de::DeserializeSeed<'de>,
    {
        Err(E::invalid_type(
            de::Unexpected::UnitVariant,
            &"newtype variant",
        ))
    }

    fn tuple_variant<V>(self, _len: usize, _visitor: V) -> Result<V::Value, Self::Error>
    where
        V: de::Visitor<'de>,
    {
        Err(E::invalid_type(
            de::Unexpected::UnitVariant,
            &"tuple variant",
        ))
    }

    fn struct_variant<V>(
        self,
        _fields: &'static [&'static str],
        _visitor: V,
    ) -> Result<V::Value, Self::Error>
    where
        V: de::Visitor<'de>,
    {
        Err(E::invalid_type(
            de::Unexpected::UnitVariant,
            &"struct variant",
        ))
    }
}

impl<'de, E> de::IntoDeserializer<'de, E> for UnitEnumAccess<E>
where
    E: de::Error,
{
    type Deserializer = de::value::EnumAccessDeserializer<UnitEnumAccess<E>>;

    fn into_deserializer(self) -> Self::Deserializer {
        de::value::EnumAccessDeserializer::new(self)
    }
}

//
// JSON and YAML test data.
//

// JSON test data that can be unambiguously converted from Bencode.
pub(crate) static REDUCED_JSON: LazyLock<serde_json::Value> = LazyLock::new(|| {
    serde_json::json!({
        "byte_string": "\\x80",
        "string": "hello world",
        "int": -1,
        "seq": [2, "foo"],
        "map": {"x": 3, "y": "bar"},
    })
});

// YAML test data that can be unambiguously converted to and from Bencode.
pub(crate) static REDUCED_YAML: LazyLock<serde_yaml::Value> = LazyLock::new(|| {
    yd([
        ("byte_string", yt("bytes", yb("\\x80"))),
        ("string", yb("hello world")),
        ("int", yi(-1)),
        ("seq", yl([yi(2), yb("foo")])),
        ("map", yd([("x", yi(3)), ("y", yb("bar"))])),
    ])
});

pub(crate) static BENCODE: LazyLock<Value<&'static [u8]>> = LazyLock::new(|| {
    vd([
        (b"byte_string", vb(b"\x80")),
        (b"string", vb(b"hello world")),
        (b"int", vi(-1)),
        (b"seq", vl([vi(2), vb(b"foo")])),
        (b"map", vd([(b"x", vi(3)), (b"y", vb(b"bar"))])),
    ])
});

// JSON test data that can be unambiguously converted to Bencode.
pub(crate) static JSON: LazyLock<serde_json::Value> = LazyLock::new(|| {
    serde_json::json!({
        "null": null,
        "false": false,
        "true": true,
        "int": -2,
        "float": 3.0f64,
        "string": "hello world",
        "seq": [4, "foo"],
        "map": {"x": 5, "y": "bar"},
    })
});

// YAML test data that can be unambiguously converted to Bencode.
pub(crate) static YAML: LazyLock<serde_yaml::Value> = LazyLock::new(|| {
    yd([
        ("null", serde_yaml::Value::Null),
        ("false", serde_yaml::Value::Bool(false)),
        ("true", serde_yaml::Value::Bool(true)),
        ("int", yi(-2)),
        ("float", serde_yaml::Value::Number(3.0f64.into())),
        ("string", yb("hello world")),
        ("seq", yl([yi(4), yb("foo")])),
        ("map", yd([("x", yi(5)), ("y", yb("bar"))])),
    ])
});

pub(crate) static EXTENDED_BENCODE: LazyLock<Value<&'static [u8]>> = LazyLock::new(|| {
    vd([
        (b"null", vl([])),
        (b"false", vi(0)),
        (b"true", vi(1)),
        (b"int", vi(-2)),
        (b"float", vi(3)),
        (b"string", vb(b"hello world")),
        (b"seq", vl([vi(4), vb(b"foo")])),
        (b"map", vd([(b"x", vi(5)), (b"y", vb(b"bar"))])),
    ])
});

// YAML test data that can be unambiguously converted to Bencode.
pub(crate) static TAG_YAML: LazyLock<serde_yaml::Value> = LazyLock::new(|| {
    let mut map = yd([
        ("int", yt("int", yi(0))),
        ("seq", yt("seq", yl([]))),
        ("map", yt("map", yd([]))),
    ]);
    map.as_mapping_mut()
        .expect("map")
        .insert(yt("bytes", yb("\\x80")), yt("bytes", yb("\\x80")));
    map
});

pub(crate) static TAG_BENCODE: LazyLock<Value<&'static [u8]>> = LazyLock::new(|| {
    vd([
        (b"\x80", vb(b"\x80")),
        // Unrecognizable tags are preserved as they are.
        (b"int", vd([(b"int", vi(0))])),
        (b"seq", vd([(b"seq", vl([]))])),
        (b"map", vd([(b"map", vd([]))])),
    ])
});

pub(crate) fn yb(value: &str) -> serde_yaml::Value {
    serde_yaml::Value::String(value.to_string())
}

pub(crate) fn yi(value: i64) -> serde_yaml::Value {
    serde_yaml::Value::Number(value.into())
}

fn yl<const N: usize>(items: [serde_yaml::Value; N]) -> serde_yaml::Value {
    serde_yaml::Value::Sequence(items.into())
}

pub(crate) fn yd<const N: usize>(items: [(&str, serde_yaml::Value); N]) -> serde_yaml::Value {
    serde_yaml::Value::Mapping(items.into_iter().map(|(k, v)| (yb(k), v)).collect())
}

pub(crate) fn yt(tag: &str, value: serde_yaml::Value) -> serde_yaml::Value {
    serde_yaml::Value::Tagged(Box::new(serde_yaml::value::TaggedValue {
        tag: serde_yaml::value::Tag::new(tag),
        value,
    }))
}
