#[cfg(target_os = "linux")]
mod linux;

use std::io::Error;

use async_trait::async_trait;

// NOTE: `sendfile` requires `in_fd` to be a file that supports mmap-like operations.  It is the
// caller's responsibility to supply an `I` that meets this requirement.
#[async_trait]
pub trait SendFile<I> {
    async fn sendfile(
        &mut self,
        input: &mut I,
        offset: Option<i64>,
        count: usize,
    ) -> Result<usize, Error>;
}

// While `Splice` is more generic than `SendFile`, based on my experiment, it is slower than
// `SendFile`.
#[async_trait]
pub trait Splice<O> {
    // NOTE: The input/output order is reversed compared to `SendFile`.
    async fn splice(&mut self, output: &mut O, count: usize) -> Result<usize, Error>;
}
