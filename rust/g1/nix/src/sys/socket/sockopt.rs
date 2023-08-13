use std::mem;
use std::os::fd::RawFd;

use libc::{c_int, c_void, setsockopt, socklen_t};
use nix::{errno::Errno, sys::socket::SetSockOpt};

use super::IpPmtudisc;

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct IpMtuDiscover;

impl SetSockOpt for IpMtuDiscover {
    type Val = IpPmtudisc;

    fn set(&self, fd: RawFd, val: &Self::Val) -> Result<(), Errno> {
        let val = *val as c_int;
        Errno::result(unsafe {
            setsockopt(
                fd,
                libc::SOL_IP,
                libc::IP_MTU_DISCOVER,
                &val as *const c_int as *const c_void,
                mem::size_of::<c_int>() as socklen_t,
            )
        })
        .map(drop)
    }
}
