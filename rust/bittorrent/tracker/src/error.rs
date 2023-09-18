use snafu::prelude::*;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    #[snafu(display("all announce urls failed"))]
    AnnounceUrlsFailed,
}
