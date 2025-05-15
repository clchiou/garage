use std::os::fd::{AsFd, AsRawFd, BorrowedFd, RawFd};

use nix::errno::Errno;
use nix::fcntl::{fcntl, OFlag, F_GETFL, F_SETFL};

/// Guards file status flags.
#[derive(Debug)]
pub struct StatusGuard<T>
where
    // TODO: Change the trait bound to `AsFd`, as [done][1] in the `nix` crate.
    // [1]: https://github.com/nix-rust/nix/pull/2434
    T: AsRawFd,
{
    fd: Option<T>,
    restore: Restore,
}

#[derive(Debug)]
struct Restore {
    original: OFlag,
    target: OFlag,
}

impl<T> StatusGuard<T>
where
    T: AsRawFd,
{
    pub fn set(fd: T, target: OFlag) -> Result<Self, Errno> {
        Self::new(fd, target, |current| current | target)
    }

    pub fn clear(fd: T, target: OFlag) -> Result<Self, Errno> {
        Self::new(fd, target, |current| current - target)
    }

    fn new(fd: T, target: OFlag, new_flag: impl Fn(OFlag) -> OFlag) -> Result<Self, Errno> {
        let raw_fd = fd.as_raw_fd();
        let current = get_status(raw_fd)?;
        let new = new_flag(current);
        if current != new {
            set_status(raw_fd, new)?;
        }
        Ok(Self {
            fd: Some(fd),
            restore: Restore::new(current, target),
        })
    }

    pub fn get_ref(&self) -> &T {
        self.fd.as_ref().unwrap()
    }

    pub fn into_inner(mut self) -> T {
        self.take_inner().unwrap()
    }

    fn take_inner(&mut self) -> Option<T> {
        let fd = self.fd.take()?;
        self.restore(fd.as_raw_fd()).unwrap();
        Some(fd)
    }

    fn restore(&self, fd: RawFd) -> Result<(), Errno> {
        let current = get_status(fd)?;
        let original = self.restore.restore(current);
        if current != original {
            set_status(fd, original)?;
        }
        Ok(())
    }
}

impl<T> AsFd for StatusGuard<T>
where
    T: AsRawFd,
{
    fn as_fd(&self) -> BorrowedFd<'_> {
        unsafe { BorrowedFd::borrow_raw(self.get_ref().as_raw_fd()) }
    }
}

impl<T> AsRawFd for StatusGuard<T>
where
    T: AsRawFd,
{
    fn as_raw_fd(&self) -> RawFd {
        self.get_ref().as_raw_fd()
    }
}

impl<T> Drop for StatusGuard<T>
where
    T: AsRawFd,
{
    fn drop(&mut self) {
        let _ = self.take_inner();
    }
}

impl Restore {
    fn new(current: OFlag, target: OFlag) -> Self {
        Self {
            original: current & target,
            target,
        }
    }

    fn restore(&self, flags: OFlag) -> OFlag {
        (flags - self.target) | self.original
    }
}

fn get_status(fd: RawFd) -> Result<OFlag, Errno> {
    let fd = unsafe { BorrowedFd::borrow_raw(fd) };
    Ok(OFlag::from_bits_retain(fcntl(fd, F_GETFL)?))
}

fn set_status(fd: RawFd, flags: OFlag) -> Result<(), Errno> {
    let fd = unsafe { BorrowedFd::borrow_raw(fd) };
    fcntl(fd, F_SETFL(flags)).map(|_| ())
}

#[cfg(test)]
mod tests {
    use libc::c_int;
    use nix::fcntl::open;
    use nix::sys::stat::Mode;
    use nix::unistd::close;

    use super::*;

    fn f(bits: c_int) -> OFlag {
        OFlag::from_bits_retain(bits)
    }

    #[test]
    fn status_guard() -> Result<(), Errno> {
        // Somehow on Linux `fcntl(F_GETFL)` also returns this.
        const UNKNOWN: OFlag = OFlag::from_bits_retain(0x8000);

        let expect = OFlag::O_TMPFILE | OFlag::O_RDWR | UNKNOWN;
        let fd = open("/tmp", OFlag::O_TMPFILE | OFlag::O_RDWR, Mode::empty())?;
        let result: Result<(), Errno> = try {
            let fd = fd.as_raw_fd();

            assert_eq!(get_status(fd)?, expect);

            let guard = StatusGuard::set(fd, OFlag::O_NONBLOCK)?;
            assert_eq!(get_status(fd)?, expect | OFlag::O_NONBLOCK);

            {
                let guard = StatusGuard::set(fd, OFlag::empty())?;
                assert_eq!(get_status(fd)?, expect | OFlag::O_NONBLOCK);

                drop(guard);
                assert_eq!(get_status(fd)?, expect | OFlag::O_NONBLOCK);
            }

            {
                let guard = StatusGuard::clear(fd, OFlag::empty())?;
                assert_eq!(get_status(fd)?, expect | OFlag::O_NONBLOCK);

                drop(guard);
                assert_eq!(get_status(fd)?, expect | OFlag::O_NONBLOCK);
            }

            {
                let guard = StatusGuard::clear(fd, OFlag::O_NONBLOCK)?;
                assert_eq!(get_status(fd)?, expect);

                drop(guard);
                assert_eq!(get_status(fd)?, expect | OFlag::O_NONBLOCK);
            }

            set_status(fd, get_status(fd)? | OFlag::O_NOATIME)?;
            assert_eq!(
                get_status(fd)?,
                expect | OFlag::O_NONBLOCK | OFlag::O_NOATIME,
            );

            drop(guard);
            assert_eq!(get_status(fd)?, expect | OFlag::O_NOATIME);
        };
        close(fd).unwrap();
        result
    }

    #[test]
    fn restore() {
        // `x - y` is not equivalent to `x & !y`.  Be sure to include this test case.
        assert_ne!(f(0x0f) - f(0x15), f(0x0f) & !f(0x15));
        for (current, target) in [
            (0x10, 0x01),
            (0x11, 0x03),
            (0x05, 0x0f),
            (0x0f, 0x15),
            (0x00, 0x00),
            (0xff, 0x00),
            (0xff, 0x01),
        ] {
            let restore = Restore::new(f(current), f(target));
            for x in 0x00..=0xff {
                assert_eq!(restore.restore(f(x)), f((x & !target) | (current & target)));
            }
        }
    }
}
