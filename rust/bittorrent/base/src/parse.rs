use std::str::FromStr;

use snafu::prelude::*;

use g1_base::str::Hex;

use crate::InfoHash;

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
