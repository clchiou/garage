use lazy_regex::regex;
use snafu::prelude::*;

use crate::InfoHash;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Error {
    #[snafu(display("invalid info hash: {info_hash:?}"))]
    InvalidInfoHash { info_hash: String },
    #[snafu(display("invalid magnet uri"))]
    InvalidMagnetUri,
    #[snafu(display("invalid urn: {urn:?}"))]
    InvalidUrn { urn: String },
    #[snafu(display("unsupported protocol: {protocol:?}"))]
    UnsupportedProtocol { protocol: String },
}

pub(super) fn parse(uri: &str) -> Result<impl Iterator<Item = (&str, &str)>, Error> {
    let query_regex = regex!(
        r"(?ix-u)
        ^
        magnet:
        (?:
            \?
            (
                (?: [[:ascii:]--[&=\#[:space:]]]* = [[:ascii:]--[&=\#[:space:]]]* )?
                (?: & [[:ascii:]--[&=\#[:space:]]]* = [[:ascii:]--[&=\#[:space:]]]* )*
                &?
            )
        )?
        (?: \# [[:ascii:]]* )?
        $
        "
    );
    let query = query_regex
        .captures(uri)
        .context(InvalidMagnetUriSnafu)?
        .get(1)
        .map_or("", |m| m.as_str());
    Ok(
        regex!(r"(?ix-u) ([[:ascii:]--[&=\#[:space:]]]*) = ([[:ascii:]--[&=\#[:space:]]]*)")
            .captures_iter(query)
            .map(|c| {
                let (_, [name, value]) = c.extract();
                (name, value)
            }),
    )
}

pub(super) fn is_exact_topic(name: &str) -> Option<Option<usize>> {
    regex!(r"(?ix-u) ^ xt (?: \. (\d+) )? $")
        .captures(name)
        .map(|captures| captures.get(1).map(|count| count.as_str().parse().unwrap()))
}

pub(super) fn parse_urn(urn: &str) -> Result<(&str, &str), Error> {
    let urn_regex = regex!(
        r"(?ix-u)
        ^
        urn:
        ( (?: - | [[:alnum:]] )+ )
        :
        ( [[:ascii:]--[?\#[:space:]]]+ )
        (?: [?\#] [[:ascii:]]* )?
        $
        "
    );
    let captures = urn_regex.captures(urn).context(InvalidUrnSnafu { urn })?;
    Ok((
        captures.get(1).unwrap().as_str(),
        captures.get(2).unwrap().as_str(),
    ))
}

pub(super) fn parse_protocol(protocol: &str) -> Result<(), Error> {
    if ["btih", "sha1"]
        .into_iter()
        .any(|supported| supported.eq_ignore_ascii_case(protocol))
    {
        Ok(())
    } else {
        Err(Error::UnsupportedProtocol {
            protocol: protocol.to_string(),
        })
    }
}

pub(super) fn parse_info_hash(info_hash: &str) -> Result<InfoHash, Error> {
    if regex!(r"(?-u)^[[:xdigit:]]{40}$").is_match(info_hash) {
        Ok(info_hash.parse().unwrap())
    } else if regex!(r"(?-u)^[A-Z2-7]{32}$").is_match(info_hash) {
        // Support Base32 for backwards compatibility.
        Ok(InfoHash::new(decode_base32(info_hash)))
    } else {
        Err(Error::InvalidInfoHash {
            info_hash: info_hash.to_string(),
        })
    }
}

fn decode_base32<const N: usize>(input: &str) -> [u8; N] {
    assert!(input.len() * 5 / 8 <= N);
    let mut output = [0; N];
    for (base, chunk) in input.as_bytes().chunks(8).enumerate() {
        let mut x = 0u64;
        for &c in chunk {
            x = (x << 5) | u64::from(base32_map(c));
        }
        x <<= (8 - chunk.len()) * 5;
        for (offset, &b) in x.to_be_bytes()[3..8].iter().enumerate() {
            let i = base * 5 + offset;
            if i < N {
                output[i] = b;
            }
        }
    }
    output
}

fn base32_map(c: u8) -> u8 {
    const CHAR_A: u8 = 65;
    const CHAR_Z: u8 = 90;
    const CHAR_2: u8 = 50;
    const CHAR_7: u8 = 55;
    if (CHAR_A..=CHAR_Z).contains(&c) {
        c - CHAR_A
    } else {
        assert!((CHAR_2..=CHAR_7).contains(&c));
        c - CHAR_2 + CHAR_Z - CHAR_A + 1
    }
}

#[cfg(test)]
mod tests {
    use hex_literal::hex;

    use super::*;

    #[test]
    fn test_parse() {
        fn test_ok(uri: &str, expect: &[(&str, &str)]) {
            assert_eq!(parse(uri).unwrap().collect::<Vec<_>>(), expect);
        }

        fn test_err(uri: &str) {
            assert!(matches!(parse(uri), Err(Error::InvalidMagnetUri)));
        }

        test_ok("magnet:", &[]);
        test_ok("MaGnEt:?", &[]);
        test_ok("magnet:?=", &[("", "")]);
        test_ok("magnet:?=&", &[("", "")]);
        test_ok("magnet:?=&=", &[("", ""), ("", "")]);
        test_ok("magnet:?p=q", &[("p", "q")]);
        test_ok("magnet:?p=q&fOo=BaR&", &[("p", "q"), ("fOo", "BaR")]);
        test_ok("magnet:?#spam egg", &[]);
        test_ok("magnet:?&#spam=egg  ", &[]);

        test_err("");
        test_err("magnet");
        test_err(" magnet:");
        test_err("magnet: ");
        test_err("magnet:?p==q");
        test_err("magnet:? =&");
        test_err("magnet:?= &");
        test_err("magnet:?&&");
    }

    #[test]
    fn test_is_exact_topic() {
        assert_eq!(is_exact_topic("xt"), Some(None));
        assert_eq!(is_exact_topic("xt.0"), Some(Some(0)));
        assert_eq!(is_exact_topic("xt.012"), Some(Some(12)));

        assert_eq!(is_exact_topic(""), None);
        assert_eq!(is_exact_topic(" xt"), None);
        assert_eq!(is_exact_topic(" xt.0"), None);
        assert_eq!(is_exact_topic("xt.0 "), None);
        assert_eq!(is_exact_topic("xt."), None);
        assert_eq!(is_exact_topic("xt.abc"), None);
    }

    #[test]
    fn test_parse_urn() {
        fn test_err(urn: &str) {
            assert_eq!(
                parse_urn(urn),
                Err(Error::InvalidUrn {
                    urn: urn.to_string(),
                }),
            );
        }

        assert_eq!(parse_urn("urn:-:."), Ok(("-", ".")));
        assert_eq!(parse_urn("urn:AbC:dEf?foo"), Ok(("AbC", "dEf")));
        assert_eq!(parse_urn("urn:1-2--3:456#bar  "), Ok(("1-2--3", "456")));

        test_err("");
        test_err(" urn:-:.");
        test_err("urn:p:q ");
    }

    #[test]
    fn test_parse_protocol() {
        fn test_err(protocol: &str) {
            assert_eq!(
                parse_protocol(protocol),
                Err(Error::UnsupportedProtocol {
                    protocol: protocol.to_string(),
                }),
            );
        }

        assert_eq!(parse_protocol("btih"), Ok(()));
        assert_eq!(parse_protocol("bTiH"), Ok(()));
        assert_eq!(parse_protocol("sha1"), Ok(()));
        assert_eq!(parse_protocol("ShA1"), Ok(()));

        test_err("");
        test_err(" btih");
        test_err("sha1 ");
        test_err("foo");

        // TODO: We do not support BitTorrent v2 (btmh) at the moment.
        test_err("btmh");
    }

    #[test]
    fn test_parse_info_hash() {
        fn test_err(info_hash: &str) {
            assert_eq!(
                parse_info_hash(info_hash),
                Err(Error::InvalidInfoHash {
                    info_hash: info_hash.to_string(),
                }),
            );
        }

        assert_eq!(
            parse_info_hash("0123456789012345678901234567890123456789"),
            Ok(InfoHash::new(hex!(
                "0123456789012345678901234567890123456789"
            ))),
        );

        assert_eq!(
            parse_info_hash("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"),
            Ok(InfoHash::new(hex!(
                "00 44 32 14 c7 42 54 b6 35 cf 84 65 3a 56 d7 c6 75 be 77 df"
            ))),
        );

        test_err("");
        test_err("_123456789012345678901234567890123456789");
        test_err("0123456789012345678901234567890123456789 ");
        test_err(" 0123456789012345678901234567890123456789 ");
        test_err("012345678901234567890123456789012345678");
        test_err("01234567890123456789012345678901234567890");
        test_err("_BCDEFGHIJKLMNOPQRSTUVWXYZ234567");
        test_err(" ABCDEFGHIJKLMNOPQRSTUVWXYZ234567");
        test_err("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567 ");
        test_err("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567A");
        test_err("ABCDEFGHIJKLMNOPQRSTUVWXYZ23456");
    }

    #[test]
    fn test_decode_base32() {
        fn to_array<const N: usize>(string: &str) -> [u8; N] {
            string.as_bytes().try_into().unwrap()
        }

        assert_eq!(decode_base32(""), [0; 0]);

        assert_eq!(decode_base32("MY"), to_array::<1>("f"));
        assert_eq!(decode_base32("MZXQ"), to_array::<2>("fo"));
        assert_eq!(decode_base32("MZXW6"), to_array::<3>("foo"));
        assert_eq!(decode_base32("MZXW6YQ"), to_array::<4>("foob"));
        assert_eq!(decode_base32("MZXW6YTB"), to_array::<5>("fooba"));
        assert_eq!(decode_base32("MZXW6YTBOI"), to_array::<6>("foobar"));

        assert_eq!(decode_base32("AA"), [0x00]);
        assert_eq!(decode_base32("AB"), [0x00]);
        assert_eq!(decode_base32("AC"), [0x00]);
        assert_eq!(decode_base32("AD"), [0x00]);

        assert_eq!(decode_base32("AE"), [0x01]);
        assert_eq!(decode_base32("AF"), [0x01]);
        assert_eq!(decode_base32("AG"), [0x01]);
        assert_eq!(decode_base32("AH"), [0x01]);

        assert_eq!(decode_base32("AI"), [0x02]);
        assert_eq!(decode_base32("AJ"), [0x02]);
        assert_eq!(decode_base32("AK"), [0x02]);
        assert_eq!(decode_base32("AL"), [0x02]);

        assert_eq!(decode_base32("AM"), [0x03]);
        assert_eq!(decode_base32("AN"), [0x03]);
        assert_eq!(decode_base32("AO"), [0x03]);
        assert_eq!(decode_base32("AP"), [0x03]);

        assert_eq!(decode_base32("AQ"), [0x04]);
        assert_eq!(decode_base32("AR"), [0x04]);
        assert_eq!(decode_base32("AS"), [0x04]);
        assert_eq!(decode_base32("AT"), [0x04]);

        assert_eq!(decode_base32("AU"), [0x05]);
        assert_eq!(decode_base32("AV"), [0x05]);
        assert_eq!(decode_base32("AW"), [0x05]);
        assert_eq!(decode_base32("AX"), [0x05]);

        assert_eq!(decode_base32("AY"), [0x06]);
        assert_eq!(decode_base32("AZ"), [0x06]);
        assert_eq!(decode_base32("A2"), [0x06]);
        assert_eq!(decode_base32("A3"), [0x06]);

        assert_eq!(decode_base32("A4"), [0x07]);
        assert_eq!(decode_base32("A5"), [0x07]);
        assert_eq!(decode_base32("A6"), [0x07]);
        assert_eq!(decode_base32("A7"), [0x07]);

        assert_eq!(decode_base32("BA"), [0x08]);

        assert_eq!(decode_base32("7Y"), [0xfe]);
        assert_eq!(decode_base32("7Z"), [0xfe]);
        assert_eq!(decode_base32("72"), [0xfe]);
        assert_eq!(decode_base32("73"), [0xfe]);

        assert_eq!(decode_base32("74"), [0xff]);
        assert_eq!(decode_base32("75"), [0xff]);
        assert_eq!(decode_base32("75"), [0xff]);
        assert_eq!(decode_base32("77"), [0xff]);

        assert_eq!(decode_base32("DEADBEEF"), hex!("19 00 30 90 85"));
        assert_eq!(decode_base32("MRSWCZDCMVSWM"), to_array::<8>("deadbeef"));
        assert_eq!(decode_base32("32W353Y"), hex!("deadbeef"));

        assert_eq!(decode_base32("HELLOWORLD"), hex!("39 16 b7 59 d1 58"));
        assert_eq!(
            decode_base32("JBCUYTCPK5HVETCE"),
            to_array::<10>("HELLOWORLD"),
        );

        assert_eq!(
            decode_base32("BAFYBEICZSSCDSBS7FFQZ55ASQDF3SMV6KLCW3GOFSZVWLYARCI47BGF354"),
            hex!(
                "08 0b 80 91 02 cc a4 21 c8 32 f9 4b 0c f7 a0 94"
                "06 5d c9 95 f2 96 2b 6c ce 2c b3 5b 2f 00 88 91"
                "cf 84 c5 df"
            ),
        );
    }

    #[test]
    fn test_base32_map() {
        const CHARS: &str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
        for (i, c) in CHARS.as_bytes().iter().copied().enumerate() {
            assert_eq!(usize::from(base32_map(c)), i);
        }
    }
}
