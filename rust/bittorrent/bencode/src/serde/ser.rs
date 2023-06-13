use std::collections::BTreeMap;
use std::ops::Deref;

use bytes::BytesMut;
use serde::{
    ser::{
        self, SerializeMap, SerializeSeq, SerializeStruct, SerializeStructVariant, SerializeTuple,
        SerializeTupleStruct, SerializeTupleVariant,
    },
    Serialize,
};
use serde_bytes::Bytes;

use g1_serde::serialize;

use crate::own::{ByteString, Dictionary, List, Value};

use super::{error::Error, to_int};

//
// Serialize
//

impl<ByteString, List, Dictionary> Serialize for crate::Value<ByteString, List, Dictionary>
where
    ByteString: AsRef<[u8]>,
    List: Deref<Target = Vec<Self>>,
    Dictionary: Deref<Target = BTreeMap<ByteString, Self>>,
{
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: ser::Serializer,
    {
        match self {
            Self::ByteString(bytes) => serializer.serialize_bytes(bytes.as_ref()),
            Self::Integer(int) => serializer.serialize_i64(*int),
            Self::List(list) => list.serialize(serializer),
            Self::Dictionary(dict) => {
                let mut map = serializer.serialize_map(Some(dict.len()))?;
                for (key, value) in dict.iter() {
                    map.serialize_entry(Bytes::new(key.as_ref()), value)?;
                }
                map.end()
            }
        }
    }
}

//
// Serializer
//

pub struct Serializer;

pub fn to_bytes<T>(value: &T) -> Result<BytesMut, Error>
where
    T: Serialize,
{
    let mut buffer = BytesMut::new();
    value.serialize(Serializer)?.encode(&mut buffer);
    Ok(buffer)
}

/// Constructs a `BTreeMap<own::ByteString, own::Value>` from an array of `(&str, own::Value)`.
macro_rules! btree_from {
    ($(($key:expr, $value:expr $(,)?)),* $(,)?) => {
        BTreeMap::<ByteString, Value>::from([$(($key.as_bytes().into(), $value)),*])
    };
}

macro_rules! serialize_int {
    ($func_root:ident) => {
        serialize!($func_root(self, value) self.serialize_i64(to_int(value)?));
    };
}

macro_rules! serialize_to_bytes {
    ($func_root:ident($value:ident) $expr:expr) => {
        serialize!($func_root(self, $value) {
            Ok(ByteString::from($expr).into())
        });
    };
}

impl ser::Serializer for Serializer {
    type Ok = Value;
    type Error = Error;

    type SerializeSeq = List;
    type SerializeTuple = List;
    type SerializeTupleStruct = List;
    type SerializeTupleVariant = Dictionary;
    type SerializeMap = Dictionary;
    type SerializeStruct = Dictionary;
    type SerializeStructVariant = Dictionary;

    serialize_int!(bool);

    serialize_int!(i8);
    serialize_int!(i16);
    serialize_int!(i32);
    serialize!(i64(self, value) Ok(value.into()));

    serialize_int!(u8);
    serialize_int!(u16);
    serialize_int!(u32);
    serialize_int!(u64);

    serde::serde_if_integer128! {
        serialize_int!(i128);
        serialize_int!(u128);
    }

    serialize_to_bytes!(f32(value) value.to_bits().to_be_bytes().as_slice());
    serialize_to_bytes!(f64(value) value.to_bits().to_be_bytes().as_slice());

    serialize!(char(self, value) {
        let mut buffer = [0u8; 4];
        value.encode_utf8(&mut buffer);
        self.serialize_u32(u32::from_le_bytes(buffer))
    });

    serialize_to_bytes!(str(value) value.as_bytes());

    serialize_to_bytes!(bytes(value) value);

    serialize!(none(self) Ok(vec![].into()));
    serialize!(some(self, value) Ok(vec![value.serialize(Serializer)?].into()));

    serialize!(unit(self) Ok(vec![].into()));
    serialize!(unit_struct(self, _name) Ok(vec![].into()));

    serialize!(unit_variant(self, _name, _variant_index, variant) self.serialize_str(variant));

    serialize!(newtype_struct(self, _name, value) value.serialize(self));

    serialize!(newtype_variant(self, _name, _variant_index, variant, value) {
        Ok(btree_from![(variant, value.serialize(self)?)].into())
    });

    serialize!(seq(self, len) Ok(List(Vec::with_capacity(len.unwrap_or(0)))));
    serialize!(tuple(self, len) Ok(List(Vec::with_capacity(len))));
    serialize!(tuple_struct(self, _name, len) Ok(List(Vec::with_capacity(len))));

    serialize!(tuple_variant(self, _name, _variant_index, variant, len) {
        Ok(Dictionary(btree_from![(
            variant,
            Vec::with_capacity(len).into()
        )]))
    });

    serialize!(map(self, _len) Ok(Dictionary(BTreeMap::new())));
    serialize!(struct(self, _name, _len) Ok(Dictionary(BTreeMap::new())));

    serialize!(struct_variant(self, _name, _variant_index, variant, _len) {
        Ok(Dictionary(btree_from![(variant, BTreeMap::new().into())]))
    });
}

impl SerializeSeq for List {
    type Ok = Value;
    type Error = Error;

    fn serialize_element<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: Serialize + ?Sized,
    {
        self.push(value.serialize(Serializer)?);
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        Ok(Value::List(self))
    }
}

impl SerializeTuple for List {
    type Ok = Value;
    type Error = Error;

    fn serialize_element<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: Serialize + ?Sized,
    {
        self.push(value.serialize(Serializer)?);
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        Ok(Value::List(self))
    }
}

impl SerializeTupleStruct for List {
    type Ok = Value;
    type Error = Error;

    fn serialize_field<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: Serialize + ?Sized,
    {
        self.push(value.serialize(Serializer)?);
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        Ok(Value::List(self))
    }
}

impl SerializeTupleVariant for Dictionary {
    type Ok = Value;
    type Error = Error;

    fn serialize_field<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: Serialize + ?Sized,
    {
        if let Value::List(list) = self.last_entry().unwrap().get_mut() {
            list.push(value.serialize(Serializer)?);
        } else {
            panic!("expect a list entry: {:?}", self);
        }
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        Ok(Value::Dictionary(self))
    }
}

impl SerializeMap for Dictionary {
    type Ok = Value;
    type Error = Error;

    fn serialize_key<T>(&mut self, key: &T) -> Result<(), Self::Error>
    where
        T: Serialize + ?Sized,
    {
        self.insert(to_byte_string(key)?, 0.into()); // Insert a dummy.
        Ok(())
    }

    fn serialize_value<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: Serialize + ?Sized,
    {
        self.last_entry()
            .unwrap()
            .insert(value.serialize(Serializer)?);
        Ok(())
    }

    fn serialize_entry<K, V>(&mut self, key: &K, value: &V) -> Result<(), Self::Error>
    where
        K: Serialize + ?Sized,
        V: Serialize + ?Sized,
    {
        self.insert(to_byte_string(key)?, value.serialize(Serializer)?);
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        Ok(Value::Dictionary(self))
    }
}

fn to_byte_string<T>(value: &T) -> Result<ByteString, Error>
where
    T: Serialize + ?Sized,
{
    match value.serialize(Serializer)? {
        Value::ByteString(value) => Ok(value),
        value => Err(Error::ExpectValueType {
            type_name: "ByteString",
            value,
        }),
    }
}

impl SerializeStruct for Dictionary {
    type Ok = Value;
    type Error = Error;

    fn serialize_field<T>(&mut self, key: &'static str, value: &T) -> Result<(), Self::Error>
    where
        T: Serialize + ?Sized,
    {
        self.insert(
            ByteString::from(key.as_bytes()),
            value.serialize(Serializer)?,
        );
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        Ok(Value::Dictionary(self))
    }
}

impl SerializeStructVariant for Dictionary {
    type Ok = Value;
    type Error = Error;

    fn serialize_field<T>(&mut self, key: &'static str, value: &T) -> Result<(), Self::Error>
    where
        T: Serialize + ?Sized,
    {
        if let Value::Dictionary(dict) = self.last_entry().unwrap().get_mut() {
            dict.insert(
                ByteString::from(key.as_bytes()),
                value.serialize(Serializer)?,
            );
        } else {
            panic!("expect a dict entry: {:?}", self);
        }
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        Ok(Value::Dictionary(self))
    }
}
