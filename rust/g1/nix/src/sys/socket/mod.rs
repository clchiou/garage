pub mod sockopt;

use std::os::fd::RawFd;

use bytes::BufMut;
use libc::{c_int, socket};
use nix::{
    errno::Errno,
    sys::socket::{AddressFamily, SockFlag},
};

/// Calls `socket(domain, SOCK_DGRAM | flags, IPPROTO_ICMP)`.
///
/// It is an (undocumented?) [Linux API].
///
/// [Linux API]: https://github.com/torvalds/linux/commit/c319b4d76b9e583a5d88d6bf190e079c4e43213d
pub fn icmp_socket(domain: AddressFamily, flags: SockFlag) -> Result<RawFd, Errno> {
    Errno::result(unsafe {
        socket(
            domain as c_int,
            libc::SOCK_DGRAM | flags.bits(),
            libc::IPPROTO_ICMP,
        )
    })
}

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
#[repr(i32)]
pub enum IpPmtudisc {
    Do = libc::IP_PMTUDISC_DO,
    Dont = libc::IP_PMTUDISC_DONT,
    Interface = libc::IP_PMTUDISC_INTERFACE,
    Omit = libc::IP_PMTUDISC_OMIT,
    Probe = libc::IP_PMTUDISC_PROBE,
    Want = libc::IP_PMTUDISC_WANT,
}

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct IcmpEchoHeader {
    pub checksum: u16,
    pub id: u16,
    pub seq: u16,
}

impl IcmpEchoHeader {
    pub const SIZE: usize = 8;

    pub const TYPE: u8 = 8;
    pub const CODE: u8 = 0;

    pub fn new(id: u16, seq: u16) -> Self {
        Self {
            checksum: 0,
            id,
            seq,
        }
    }

    pub fn update_checksum(&mut self, payload: &[u8]) {
        // RFC 1071 specifies that the checksum is calculated with the checksum field set to 0.
        self.checksum = 0;
        self.checksum = compute_checksum(self.encode().iter().chain(payload.iter()).copied());
    }

    pub fn encode(&self) -> [u8; Self::SIZE] {
        let mut header = [0u8; Self::SIZE];
        let mut buffer = header.as_mut_slice();
        buffer.put_u8(Self::TYPE);
        buffer.put_u8(Self::CODE);
        buffer.put_u16(self.checksum);
        buffer.put_u16(self.id);
        buffer.put_u16(self.seq);
        header
    }
}

/// Computes an RFC 1071 checksum.
fn compute_checksum<T>(data: T) -> u16
where
    T: Iterator<Item = u8>,
{
    let mut checksum = 0;
    for (i, datum) in data.enumerate() {
        let mut datum = u32::from(datum);
        if (i & 1) == 0 {
            datum <<= 8;
        }
        checksum += datum;
    }
    let mut carry = checksum >> 16;
    while carry != 0 {
        checksum = (checksum & 0xffff) + carry;
        carry = checksum >> 16;
    }
    checksum = !checksum;
    u16::try_from(checksum & 0xffff).unwrap()
}

#[cfg(test)]
mod tests {
    use hex_literal::hex;

    use super::*;

    #[test]
    fn encode() {
        assert_eq!(
            IcmpEchoHeader {
                checksum: 0x1234,
                id: 0x5678,
                seq: 0x9abc,
            }
            .encode(),
            hex!("08 00 1234 5678 9abc"),
        );
    }

    #[test]
    fn test_compute_checksum() {
        assert_eq!(
            compute_checksum(hex!("4500 0073 0000 4000 4011 0000 c0a8 0001 c0a8 00c7").into_iter()),
            0xb861,
        );
    }
}
