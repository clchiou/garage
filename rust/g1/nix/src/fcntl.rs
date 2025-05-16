use std::os::fd::{AsFd, BorrowedFd};

use nix::errno::Errno;
use nix::fcntl::{fcntl, OFlag, F_GETFL, F_SETFL};

/// Guards file status flags.
#[derive(Debug)]
pub struct StatusGuard<Fd>
where
    Fd: AsFd,
{
    fd: Option<Fd>,
    restore: Restore,
}

#[derive(Debug)]
struct Restore {
    original: OFlag,
    target: OFlag,
}

impl<Fd> StatusGuard<Fd>
where
    Fd: AsFd,
{
    pub fn set(fd: Fd, target: OFlag) -> Result<Self, Errno> {
        Self::new(fd, target, |current| current | target)
    }

    pub fn clear(fd: Fd, target: OFlag) -> Result<Self, Errno> {
        Self::new(fd, target, |current| current - target)
    }

    fn new(fd: Fd, target: OFlag, new_flag: impl Fn(OFlag) -> OFlag) -> Result<Self, Errno> {
        let current = get_status(&fd)?;
        let new = new_flag(current);
        if current != new {
            set_status(&fd, new)?;
        }
        Ok(Self {
            fd: Some(fd),
            restore: Restore::new(current, target),
        })
    }

    pub fn get_ref(&self) -> &Fd {
        self.fd.as_ref().expect("fd")
    }

    pub fn into_inner(mut self) -> Fd {
        self.take_inner().expect("fd")
    }

    fn take_inner(&mut self) -> Option<Fd> {
        let fd = self.fd.take()?;
        self.restore(&fd).expect("restore");
        Some(fd)
    }

    fn restore(&self, fd: &Fd) -> Result<(), Errno> {
        let current = get_status(fd)?;
        let original = self.restore.restore(current);
        if current != original {
            set_status(fd, original)?;
        }
        Ok(())
    }
}

impl<Fd> AsFd for StatusGuard<Fd>
where
    Fd: AsFd,
{
    fn as_fd(&self) -> BorrowedFd<'_> {
        self.get_ref().as_fd()
    }
}

impl<Fd> Drop for StatusGuard<Fd>
where
    Fd: AsFd,
{
    fn drop(&mut self) {
        drop(self.take_inner());
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

fn get_status<Fd: AsFd>(fd: Fd) -> Result<OFlag, Errno> {
    Ok(OFlag::from_bits_retain(fcntl(fd, F_GETFL)?))
}

fn set_status<Fd: AsFd>(fd: Fd, flags: OFlag) -> Result<(), Errno> {
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
            let fd = &fd;

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
