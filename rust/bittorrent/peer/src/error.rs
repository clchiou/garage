use snafu::prelude::*;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Error {
    #[snafu(display("peer actor is cancelled"))]
    Cancelled,
    #[snafu(display("peer agent shutdown grace period is exceeded"))]
    ShutdownGracePeriodExceeded,

    #[snafu(display("peer keep alive timeout"))]
    KeepAliveTimeout,
}
