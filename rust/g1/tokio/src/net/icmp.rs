use std::io::{Error, IoSlice, IoSliceMut};
use std::net::{Ipv4Addr, SocketAddrV4};
use std::os::fd::{AsFd, AsRawFd, RawFd};

use libc::sockaddr_in;
use nix::{
    errno::Errno,
    sys::socket::{
        recvfrom, recvmsg, sendmsg, setsockopt, sockopt::Ipv4RecvErr, AddressFamily,
        ControlMessageOwned, MsgFlags, SockFlag, SockaddrIn,
    },
    unistd::close,
};
use tokio::io::unix::AsyncFd;

use g1_nix::sys::socket::{icmp_socket, sockopt::IpMtuDiscover};

pub use libc::sock_extended_err;

pub use g1_nix::sys::socket::{IcmpEchoHeader, IpPmtudisc};

// TODO: Support IPv6.
#[derive(Debug)]
pub struct IcmpSocket {
    fd: AsyncFd<RawFd>,
}

impl IcmpSocket {
    pub fn new() -> Result<Self, Error> {
        let fd = icmp_socket(
            AddressFamily::Inet,
            SockFlag::SOCK_CLOEXEC | SockFlag::SOCK_NONBLOCK,
        )?;
        Ok(Self {
            fd: AsyncFd::new(fd).inspect_err(|_| close(fd).unwrap())?,
        })
    }

    pub fn set_mtu_discover(&self, pmtudisc: IpPmtudisc) -> Result<(), Error> {
        setsockopt(&self.fd, IpMtuDiscover, &pmtudisc).map_err(Error::from)
    }

    pub fn set_recverr(&self, recv_err: bool) -> Result<(), Error> {
        setsockopt(&self.fd, Ipv4RecvErr, &recv_err).map_err(Error::from)
    }

    pub async fn recv_from(&self, buffer: &mut [u8]) -> Result<(usize, Ipv4Addr), Error> {
        loop {
            let mut guard = self.fd.readable().await?;
            match guard.try_io(|fd| match recvfrom::<SockaddrIn>(*fd.get_ref(), buffer) {
                Ok((num_bytes_recv, peer_endpoint)) => {
                    let peer_endpoint = peer_endpoint.unwrap();
                    assert_eq!(peer_endpoint.port(), 0);
                    Ok((num_bytes_recv, peer_endpoint.ip()))
                }
                Err(errno) => Err(errno.into()),
            }) {
                Ok(result) => return result,
                Err(_) => continue, // `readmsg` returns `WouldBlock`.
            }
        }
    }

    /// Reads from the socket error queue.
    ///
    /// It is not async because reading from the error queue is inherently a non-blocking
    /// operation, as stated in section 2.1.1.5 "Blocking Read" of the [kernel documentation].
    ///
    /// [kernel documentation]: https://www.kernel.org/doc/Documentation/networking/timestamping.txt
    pub fn next_error(
        &self,
        buffer: &mut [u8],
    ) -> Option<(usize, Option<Ipv4Addr>, sock_extended_err)> {
        let mut io_slices = [IoSliceMut::new(buffer)];
        let mut cmsg_buffer = nix::cmsg_space!(sock_extended_err, Option<sockaddr_in>);
        let message = match recvmsg::<SockaddrIn>(
            self.fd.as_fd().as_raw_fd(),
            &mut io_slices,
            Some(&mut cmsg_buffer),
            MsgFlags::MSG_ERRQUEUE,
        ) {
            Ok(message) => message,
            Err(Errno::EAGAIN) => return None,
            Err(errno) => {
                std::panic!("unexpected error when reading from the socket error queue: {errno:?}");
            }
        };

        let peer_endpoint = message.address.map(|peer_endpoint| {
            assert_eq!(peer_endpoint.port(), 0);
            peer_endpoint.ip()
        });

        let mut cmsgs = message.cmsgs().expect("expect cmsgs");
        let error = match cmsgs.next().unwrap() {
            ControlMessageOwned::Ipv4RecvErr(error, _) => error,
            cmsg => std::panic!("unexpected cmsg: {cmsg:?}"),
        };
        assert_eq!(cmsgs.next(), None);

        Some((message.bytes, peer_endpoint, error))
    }

    pub async fn send_to(
        &self,
        header: &IcmpEchoHeader,
        payload: &[u8],
        peer_endpoint: Ipv4Addr,
    ) -> Result<usize, Error> {
        let header = header.encode();
        let iov = [IoSlice::new(&header), IoSlice::new(payload)];
        let flags = MsgFlags::empty();
        let peer_endpoint = SockaddrIn::from(SocketAddrV4::new(peer_endpoint, 0));
        loop {
            let mut guard = self.fd.writable().await?;
            match guard.try_io(|fd| {
                sendmsg(*fd.get_ref(), &iov, &[], flags, Some(&peer_endpoint)).map_err(Error::from)
            }) {
                Ok(result) => return result,
                Err(_) => continue, // `sendmsg` returns `WouldBlock`.
            }
        }
    }
}

impl Drop for IcmpSocket {
    fn drop(&mut self) {
        close(self.fd.as_fd().as_raw_fd()).unwrap();
    }
}
