use std::io::{self, Write};

use serde::Serialize;
use serde_json::ser::Formatter;
use serde_json::{Error, Serializer};

/// Escapes non-ASCII characters.
///
/// [`serde_json`][#907] declines to implement this feature (I guess this is because [JSON] only
/// requires characters to be encoded in UTF-8 and does not require escaping).  In some use cases,
/// it is handier to escape non-ASCII characters than to encode them as an UTF-8 sequence.
///
/// [#907]: https://github.com/serde-rs/json/issues/907
/// [JSON]: https://datatracker.ietf.org/doc/html/rfc8259#section-8.1
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct EscapeNonAscii;

impl Formatter for EscapeNonAscii {
    fn write_string_fragment<W>(&mut self, writer: &mut W, fragment: &str) -> Result<(), io::Error>
    where
        W: ?Sized + Write,
    {
        for ch in fragment.chars() {
            if ch.is_ascii() {
                writer.write_all(ch.encode_utf8(&mut [0; 4]).as_bytes())?;
            } else {
                for escape in ch.encode_utf16(&mut [0; 2]) {
                    std::write!(writer, "\\u{escape:04x}")?;
                }
            }
        }
        Ok(())
    }
}

pub fn to_string<T>(value: &T) -> Result<String, Error>
where
    T: ?Sized + Serialize,
{
    let vec = to_vec(value)?;
    // `serde_json` does not emit invalid UTF-8.
    Ok(unsafe { String::from_utf8_unchecked(vec) })
}

pub fn to_vec<T>(value: &T) -> Result<Vec<u8>, Error>
where
    T: ?Sized + Serialize,
{
    let mut writer = Vec::with_capacity(128);
    to_writer(&mut writer, value)?;
    Ok(writer)
}

pub fn to_writer<W, T>(writer: W, value: &T) -> Result<(), Error>
where
    W: Write,
    T: ?Sized + Serialize,
{
    value.serialize(&mut Serializer::with_formatter(writer, EscapeNonAscii))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn escape_non_ascii() {
        fn test(testdata: &str, expect: &str) {
            let output = to_string(testdata).unwrap();
            assert_eq!(output, expect);
            assert_eq!(serde_json::from_str::<String>(&output).unwrap(), testdata);
        }

        test("", r#""""#);
        test("Hello, World!", r#""Hello, World!""#);
        test("\t\r\n", r#""\t\r\n""#);
        test("\u{1f610}", r#""\ud83d\ude10""#);
        test("\u{2028}\u{2029}", r#""\u2028\u2029""#);
    }
}
