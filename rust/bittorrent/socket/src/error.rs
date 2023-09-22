use std::io;

use snafu::prelude::*;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    #[snafu(display("expect message {id} size == {expect}: {size}"))]
    ExpectSizeEqual { id: u8, size: u32, expect: u32 },
    #[snafu(display("expect message {id} size >= {expect}: {size}"))]
    ExpectSizeGreaterOrEqual { id: u8, size: u32, expect: u32 },
    #[snafu(display("expect message size <= {limit}: {size}"))]
    SizeExceededLimit { size: u32, limit: usize },
    #[snafu(display("unknown id: {id}"))]
    UnknownId { id: u8 },
}

impl From<Error> for io::Error {
    fn from(error: Error) -> Self {
        Self::other(error)
    }
}
