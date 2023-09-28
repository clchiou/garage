use snafu::prelude::*;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Error {
    #[snafu(display("peer keep alive timeout"))]
    KeepAliveTimeout,
}
