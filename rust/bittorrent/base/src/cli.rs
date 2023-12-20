use snafu::prelude::*;

use g1_base::str::Hex;

use crate::InfoHash;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("invalid info hash hex string: {hex:?}"))]
pub struct InfoHashParserError {
    hex: String,
}

impl InfoHash {
    pub fn cli_parse(hex: &str) -> Result<Self, InfoHashParserError> {
        let hex = Hex::try_from(hex).map_err(|hex| InfoHashParserError {
            hex: hex.to_string(),
        })?;
        Ok(InfoHash::new(hex.into_inner()))
    }
}
