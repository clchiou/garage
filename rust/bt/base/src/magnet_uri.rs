use std::borrow::Cow;
use std::fmt;
use std::str::FromStr;
use std::sync::Arc;

use serde::{Deserialize, Deserializer, Serialize, Serializer, de};
use snafu::prelude::*;
use url::Url;

use g1_base::collections::LilVec;
use g1_base::iter::IteratorExt;

use crate::info_hash::InfoHash;

// We do not derive `PartialEq` because URI parameters are generally assumed to be unordered.
#[derive(Clone, Debug)]
pub struct MagnetUri {
    // We keep the original URI because we do not currently fully parse it.
    original: Arc<str>,

    info_hashes: LilVec<InfoHash, 2>,
    // TODO: Add the rest of the parameters.
}

impl fmt::Display for MagnetUri {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.original)
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("invalid magnet uri: {magnet_uri:?}"))]
pub struct ParseMagnetUriError {
    magnet_uri: String,
}

fn parse(magnet_uri: String) -> Result<MagnetUri, ParseMagnetUriError> {
    let Some(uri) = parse_magnet_uri(&magnet_uri) else {
        return Err(ParseMagnetUriError { magnet_uri });
    };

    let Some(info_hashes): Option<LilVec<_, _>> = iter_xt_urn(&uri)
        .map(|urn| parse_xt_urn(&urn))
        .try_collect()
    else {
        return Err(ParseMagnetUriError { magnet_uri });
    };
    ensure!(!info_hashes.is_empty(), ParseMagnetUriSnafu { magnet_uri });

    Ok(MagnetUri {
        original: magnet_uri.into(),
        info_hashes,
    })
}

//
// `Url::parse` seems sufficient to parse Magnet URIs and `xt` URNs.
//
// I am not sure this is a good idea, but the parser is case-insensitive.
//

fn parse_magnet_uri(uri: &str) -> Option<Url> {
    let uri = Url::parse(uri).ok()?;
    (uri.scheme().eq_ignore_ascii_case("magnet") && uri.cannot_be_a_base() && uri.path().is_empty())
        .then_some(uri)
}

fn iter_xt_urn(uri: &Url) -> impl Iterator<Item = Cow<'_, str>> {
    uri.query_pairs()
        .filter_map(|(name, value)| {
            let (_, count) = lazy_regex::regex_captures!(r"(?ix-u) ^ xt (?: \. (\d+) )? $", &name)?;
            Some((count.parse().unwrap_or(-1), value))
        })
        .collect_then_sort_by_key(|(count, _)| *count)
        .into_iter()
        .map(|(_, urn)| urn)
}

fn parse_xt_urn(urn: &str) -> Option<InfoHash> {
    let urn = Url::parse(urn).ok()?;
    if !(urn.scheme().eq_ignore_ascii_case("urn") && urn.cannot_be_a_base()) {
        return None;
    }

    let (_, info_hash, info_hash_base32) = lazy_regex::regex_captures!(
        r#"(?x-u)
        ^
        (?: (?i) btih | sha1 )
        :
        (?: ([[:xdigit:]]{40}) | ([A-Z2-7]{32}) )
        $
        "#,
        urn.path(),
    )?;

    Some(if !info_hash.is_empty() {
        info_hash.parse().expect("info hash")
    } else {
        // Support Base32 for backwards compatibility.
        decode_base32(info_hash_base32.as_bytes()).into()
    })
}

impl FromStr for MagnetUri {
    type Err = ParseMagnetUriError;

    fn from_str(magnet_uri: &str) -> Result<Self, Self::Err> {
        parse(magnet_uri.to_string())
    }
}

impl<'de> Deserialize<'de> for MagnetUri {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        parse(String::deserialize(deserializer)?).map_err(de::Error::custom)
    }
}

impl Serialize for MagnetUri {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(&self.original)
    }
}

impl MagnetUri {
    pub fn info_hashes(&self) -> &[InfoHash] {
        &self.info_hashes
    }
}

// Given the current state of third-party crates and our use case, implementing Base32 ourselves
// seems more reasonable.
fn decode_base32<const N: usize>(base32: &[u8]) -> [u8; N] {
    assert_eq!(
        base32.len() * 5,
        N * 8,
        "padding is not implemented for now",
    );
    let mut bytes = [0; N];
    for (bytes, base32) in bytes.chunks_mut(5).zip(base32.chunks(8)) {
        let mut buffer = 0u64;
        for c in base32 {
            buffer = (buffer << 5) | u64::from(decode_base32_char(*c));
        }
        bytes.copy_from_slice(&buffer.to_be_bytes()[3..8]);
    }
    bytes
}

// RFC 4648 Base32 Alphabet
fn decode_base32_char(c: u8) -> u8 {
    match c {
        b'A'..=b'Z' => c - b'A',
        b'2'..=b'7' => c - b'2' + b'Z' - b'A' + 1,
        _ => std::panic!("expect base32 character: '{}'", c.escape_ascii()),
    }
}

#[cfg(test)]
mod tests {
    use hex_literal::hex;

    use super::*;

    #[test]
    fn test_parse() {
        fn test_ok(magnet_uri: &str, expect: &[InfoHash]) {
            let actual = parse(magnet_uri.to_string()).unwrap();
            assert_eq!(&*actual.original, magnet_uri);
            assert_eq!(&*actual.info_hashes, expect);
        }

        fn test_err(magnet_uri: &str) {
            assert_eq!(
                parse(magnet_uri.to_string()).unwrap_err(),
                ParseMagnetUriError {
                    magnet_uri: magnet_uri.to_string(),
                },
            );
        }

        test_ok(
            "magNET:?xt=urn:btih:000102030405060708090a0b0c0d0e0fDEADBEEF#foobar",
            &[hex!("000102030405060708090a0b0c0d0e0f deadbeef").into()],
        );
        test_ok(
            "magnet:?spam=egg&xt.0=URN:BTIH:000102030405060708090a0b0c0d0e0fDEADBEEF&XT=urn:SHA1:ABCDEFGHIJKLMNOPQRSTUVWXYZ234567&foo=bar",
            &[
                hex!("00443214c7 4254b635cf 84653a56d7 c675be77df").into(),
                hex!("000102030405060708090a0b0c0d0e0f deadbeef").into(),
            ],
        );

        test_err("");
        test_err("magnet:");
        test_err("magnet:xt=urn:btih:");
    }

    #[test]
    fn test_parse_magnet_uri() {
        for testdata in [
            "magnet:",
            "MaGnEt:?",
            "mAgNeT:#foobar",
            "magnet:?xt=urn:btih:000102030405060708090a0b0c0d0e0fDEADBEEF#foobar",
        ] {
            assert!(
                parse_magnet_uri(testdata).is_some(),
                "testdata: {testdata:?}"
            );
        }

        for testdata in [
            "",
            "http:",
            "magnet:///?xt=123",
            "magnet:btih:000102030405060708090a0b0c0d0e0fDEADBEEF",
        ] {
            assert!(
                parse_magnet_uri(testdata).is_none(),
                "testdata: {testdata:?}"
            );
        }
    }

    #[test]
    fn test_iter_xt_urn() {
        fn test(testdata: &str, expect: &[&str]) {
            assert_eq!(
                iter_xt_urn(&Url::parse(&std::format!("magnet:?{testdata}")).unwrap())
                    .collect::<Vec<_>>(),
                expect,
            );
        }

        test("", &[]);

        test("xt.=1", &[]);
        test("xt.a=1", &[]);

        test("xt=spam", &["spam"]);
        test("xt.999=egg", &["egg"]);
        test("xT=foo&Xt=bar", &["foo", "bar"]);

        test("spam&XT.0=a&egg&xt.0=b&foo", &["a", "b"]);
        test("spam&xt.1=a&egg&XT=b&xt.0=c&foo", &["b", "c", "a"]);
    }

    #[test]
    fn test_parse_xt_urn() {
        assert_eq!(
            parse_xt_urn("UrN:bTiH:000102030405060708090a0b0c0d0e0fDEADBEEF?x=y#z"),
            Some(hex!("000102030405060708090a0b0c0d0e0f deadbeef").into()),
        );
        assert_eq!(
            parse_xt_urn("uRn:ShA1:ABCDEFGHIJKLMNOPQRSTUVWXYZ234567?x=y#z"),
            Some(hex!("00443214c7 4254b635cf 84653a56d7 c675be77df").into()),
        );

        for testdata in [
            "",
            "http:btih:000102030405060708090a0b0c0d0e0fDEADBEEF",
            "urn:foobar:000102030405060708090a0b0c0d0e0fDEADBEEF",
            "urn:///btih:000102030405060708090a0b0c0d0e0fDEADBEEF",
            // Wrong hex or base32 char
            "urn:btih:XYZ102030405060708090a0b0c0d0e0fDEADBEEF",
            "urn:btih:abcdefghijklmnopqrstuvwxyz234567",
            "urn:btih:ABCDEFGHIJKLMNOPQRSTUVWXYZ018922",
            // Wrong length
            "urn:btih:000102030405060708090a0b0c0d0e0fDEADBEE",
            "urn:btih:000102030405060708090a0b0c0d0e0fDEADBEEF0",
            "urn:sha1:ABCDEFGHIJKLMNOPQRSTUVWXYZ2345",
            "urn:sha1:ABCDEFGHIJKLMNOPQRSTUVWXYZ234567A",
        ] {
            assert_eq!(parse_xt_urn(testdata), None, "testdata: {testdata:?}");
        }
    }

    #[test]
    fn test_decode_base32() {
        assert_eq!(decode_base32(b""), hex!(""));
        assert_eq!(decode_base32(b"7A7H7A7H"), hex!("f8 3e 7f 83 e7"));
        assert_eq!(decode_base32(b"O7A7O7A7"), hex!("77 c1 f7 7c 1f"));
        assert_eq!(decode_base32(b"MZXW6YTB"), *b"fooba");
        assert_eq!(decode_base32(b"DEADBEEF"), hex!("19 00 30 90 85"));
        assert_eq!(
            decode_base32(b"DEADBEEF7A7H7A7H"),
            hex!("19 00 30 90 85 f8 3e 7f 83 e7"),
        );
        assert_eq!(
            decode_base32(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"),
            hex!("00443214c7 4254b635cf 84653a56d7 c675be77df"),
        );
    }

    #[test]
    #[should_panic(expected = "padding is not implemented for now")]
    fn test_decode_base32_padding() {
        assert_eq!(decode_base32(b"A"), hex!(""));
    }

    #[test]
    fn test_decode_base32_char() {
        assert_eq!(decode_base32_char(b'A'), 0);
        assert_eq!(decode_base32_char(b'B'), 1);
        assert_eq!(decode_base32_char(b'Z'), 25);
        assert_eq!(decode_base32_char(b'2'), 26);
        assert_eq!(decode_base32_char(b'3'), 27);
        assert_eq!(decode_base32_char(b'7'), 31);
    }

    #[test]
    #[should_panic(expected = "expect base32 character: '8'")]
    fn test_decode_base32_char_invalid_input() {
        decode_base32_char(b'8');
    }
}
