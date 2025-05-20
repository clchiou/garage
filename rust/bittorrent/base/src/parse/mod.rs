pub mod magnet_uri;

use std::str::FromStr;

use snafu::prelude::*;

use g1_base::str::Hex;

use crate::{InfoHash, MagnetUri};

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("{error} {uri:?}"))]
pub struct ParseMagnetUriError {
    #[snafu(source)]
    error: magnet_uri::Error,
    uri: String,
}

impl FromStr for MagnetUri {
    type Err = ParseMagnetUriError;

    fn from_str(uri: &str) -> Result<Self, Self::Err> {
        let mut info_hashes = Vec::new();
        let result: Result<_, _> = try {
            for (name, value) in magnet_uri::parse(uri)? {
                if magnet_uri::is_exact_topic(name).is_some() {
                    let (protocol, info_hash) = magnet_uri::parse_urn(value)?;
                    magnet_uri::parse_protocol(protocol)?;
                    let info_hash = magnet_uri::parse_info_hash(info_hash)?;
                    if !info_hashes.contains(&info_hash) {
                        info_hashes.push(info_hash);
                    }
                }
            }
        };
        result.context(ParseMagnetUriSnafu { uri })?;
        Ok(Self { info_hashes })
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("invalid info hash hex string: {hex:?}"))]
pub struct ParseInfoHashError {
    hex: String,
}

impl FromStr for InfoHash {
    type Err = ParseInfoHashError;

    fn from_str(hex: &str) -> Result<Self, Self::Err> {
        let hex = Hex::try_from(hex).map_err(|hex| Self::Err {
            hex: hex.to_string(),
        })?;
        Ok(Self::new(hex.into_inner()))
    }
}

#[cfg(test)]
mod tests {
    use hex_literal::hex;

    use super::*;

    #[test]
    fn magnet_uri() {
        fn test_err(uri: &str, error: magnet_uri::Error) {
            assert_eq!(
                MagnetUri::from_str(uri),
                Err(ParseMagnetUriError {
                    error,
                    uri: uri.to_string(),
                }),
            );
        }

        assert_eq!(
            MagnetUri::from_str("magnet:"),
            Ok(MagnetUri {
                info_hashes: vec![],
            }),
        );
        assert_eq!(
            MagnetUri::from_str(
                "magnet:?xt=urn:btih:0123456789012345678901234567890123456789&what=ever"
            ),
            Ok(MagnetUri {
                info_hashes: vec![InfoHash::new(hex!(
                    "0123456789012345678901234567890123456789"
                ))],
            }),
        );
        assert_eq!(
            MagnetUri::from_str(
                "magnet:?xt.1=urn:btih:0123456789012345678901234567890123456789&what=ever&xt.2=urn:sha1:ABCDEFGHIJKLMNOPQRSTUVWXYZ234567#foobar"
            ),
            Ok(MagnetUri {
                info_hashes: vec![
                    InfoHash::new(hex!("0123456789012345678901234567890123456789")),
                    InfoHash::new(hex!(
                        "00 44 32 14 c7 42 54 b6 35 cf 84 65 3a 56 d7 c6 75 be 77 df"
                    )),
                ],
            }),
        );

        test_err("", magnet_uri::Error::InvalidMagnetUri);
        test_err(
            "magnet:?xt=urn/btmh/0123456789012345678901234567890123456789",
            magnet_uri::Error::InvalidUrn {
                urn: "urn/btmh/0123456789012345678901234567890123456789".to_string(),
            },
        );
        test_err(
            "magnet:?xt=urn:btmh:0123456789012345678901234567890123456789",
            magnet_uri::Error::UnsupportedProtocol {
                protocol: "btmh".to_string(),
            },
        );
        test_err(
            "magnet:?xt=urn:btih:012345678901234567890123456789012345678",
            magnet_uri::Error::InvalidInfoHash {
                info_hash: "012345678901234567890123456789012345678".to_string(),
            },
        );
    }
}
