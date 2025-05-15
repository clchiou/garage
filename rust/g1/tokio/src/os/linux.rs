use std::io::Error;
use std::os::fd::{AsFd, AsRawFd, BorrowedFd};

use async_trait::async_trait;
use nix::fcntl::{splice, OFlag, SpliceFFlags};
use nix::sys::sendfile::sendfile;
use nix::unistd::pipe2;
use tokio::io::unix::AsyncFd;
use tokio::task;

use g1_nix::fcntl::StatusGuard;

use crate::task::{Cancel, JoinGuard};

use super::{SendFile, Splice};

#[async_trait]
impl<I, O> SendFile<I> for O
where
    I: AsFd + Send,
    O: AsFd + Send,
{
    async fn sendfile(
        &mut self,
        input: &mut I,
        mut offset: Option<i64>,
        count: usize,
    ) -> Result<usize, Error> {
        //
        // Based on my experiment, non-blocking `sendfile` calls are faster than blocking calls,
        // which contrasts with `splice`, though the reasons for this difference are currently
        // unknown to me.
        //

        // Ensure that if `sendfile` returns `EAGAIN`, it must be due to `self` and not `input`.
        let input = &StatusGuard::clear(input.as_fd(), OFlag::O_NONBLOCK)?;
        let output = AsyncFd::new(StatusGuard::set(self.as_fd(), OFlag::O_NONBLOCK)?)?;

        let mut size = 0;
        while count > size {
            if let Ok(n) = output
                .writable()
                .await?
                .try_io(|output| Ok(sendfile(output, input, offset.as_mut(), count - size)?))
            {
                match n? {
                    0 => break,
                    n => size += n,
                }
            }
        }
        Ok(size)
    }
}

#[async_trait]
impl<I, O> Splice<O> for I
where
    I: AsFd + Send,
    O: AsFd + Send,
{
    async fn splice(&mut self, output: &mut O, count: usize) -> Result<usize, Error> {
        //
        // We make blocking calls to `splice` for two reasons:
        //
        // * On `self`-to-`w` half: If we were to register them with the tokio reactor and make
        //   non-blocking calls, it would not be possible to correctly clear the tokio readiness
        //   flags because when `splice` returns `EAGAIN`, it does not indicate whether it is
        //   `self`, `w`, or both that are blocking.
        //
        // * On `r`-to-`output` half: I have experimented with fixing the `output` to the `File`
        //   type and made non-blocking `splice` calls.  However, the results are slower, and the
        //   reasons for this slowdown are unknown to me.
        //
        let input_guard = StatusGuard::clear(self.as_fd(), OFlag::O_NONBLOCK)?;
        let output_guard = StatusGuard::clear(output.as_fd(), OFlag::O_NONBLOCK)?;

        let i = input_guard.as_raw_fd();
        let o = output_guard.as_raw_fd();
        let (r, w) = pipe2(OFlag::O_CLOEXEC)?;

        //
        // We guard `splice_all` tasks with `JoinGuard` so that if the input or output file
        // descriptors are closed due to the cancellation of the calling task, `splice_all` will
        // stop promptly.  (There are race conditions if `splice_all` does not stop.)
        //

        let cancel = Cancel::new();
        let mut i_guard = JoinGuard::new(
            {
                let cancel = cancel.clone();
                task::spawn_blocking(move || splice_all(cancel, &i, &w, count))
            },
            cancel,
        );

        let cancel = Cancel::new();
        let mut o_guard = JoinGuard::new(
            {
                let cancel = cancel.clone();
                task::spawn_blocking(move || splice_all(cancel, &r, &o, count))
            },
            cancel,
        );

        tokio::try_join!(
            async {
                i_guard.join().await;
                i_guard.take_result().unwrap()
            },
            async {
                o_guard.join().await;
                o_guard.take_result().unwrap()
            },
        )
        .map(|sizes| {
            assert_eq!(sizes.0, sizes.1);
            sizes.0
        })
    }
}

fn splice_all<I, O>(cancel: Cancel, input: &I, output: &O, count: usize) -> Result<usize, Error>
where
    // TODO: Change the trait bound to `AsFd`, as [done][1] in the `nix` crate.
    // [1]: https://github.com/nix-rust/nix/pull/2434
    I: AsRawFd,
    O: AsRawFd,
{
    // NOTE: We do not set `SPLICE_F_NONBLOCK` here and it is the caller's responsibility to set or
    // clear `O_NONBLOCK` on input and output.
    const FLAG: SpliceFFlags = SpliceFFlags::SPLICE_F_MOVE;

    let i = unsafe { BorrowedFd::borrow_raw(input.as_raw_fd()) };
    let o = unsafe { BorrowedFd::borrow_raw(output.as_raw_fd()) };

    let mut size = 0;
    while count > size && !cancel.is_set() {
        match splice(i, None, o, None, count - size, FLAG)? {
            0 => break,
            n => size += n,
        }
    }
    Ok(size)
}
