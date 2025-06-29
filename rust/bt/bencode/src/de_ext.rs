use serde::de::{self, Unexpected, Visitor};

pub(crate) trait VisitorExt<'de>: Visitor<'de> {
    fn visit_bool_i64<E>(self, value: i64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        match value {
            0 => self.visit_bool(false),
            1 => self.visit_bool(true),
            _ => Err(E::invalid_value(Unexpected::Signed(value), &self)),
        }
    }

    fn visit_char_bytes<E>(self, value: &[u8]) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        let c = str::from_utf8(value)
            .ok()
            .and_then(|string| {
                let mut chars = string.chars();
                let c = chars.next()?;
                match chars.next() {
                    None => Some(c),
                    Some(_) => None,
                }
            })
            .ok_or_else(|| E::invalid_value(Unexpected::Bytes(value), &self))?;
        self.visit_char(c)
    }
}

impl<'de, V> VisitorExt<'de> for V where V: Visitor<'de> {}
