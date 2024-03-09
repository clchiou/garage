use std::io::{Error, ErrorKind};
use std::net::{IpAddr, SocketAddr};
use std::panic;

use tokio::sync::mpsc::{self, Receiver, Sender};
use tokio::time;

use g1_tokio::net::icmp::{IcmpEchoHeader, IcmpSocket, IpPmtudisc};
use g1_tokio::task::{Cancel, JoinGuard};

#[derive(Debug)]
pub(crate) struct PathMtuProber {
    pub(crate) probe_send: Sender<SocketAddr>,
    pub(crate) path_mtu_recv: Receiver<(SocketAddr, usize)>,
}

pub(crate) type PathMtuProberGuard = JoinGuard<()>;

// TODO: Support IPv6.
#[derive(Debug)]
struct Actor {
    cancel: Cancel,
    socket: IcmpSocket,
    probe_recv: Receiver<SocketAddr>,
    path_mtu_send: Sender<(SocketAddr, usize)>,
}

const IP_HEADER_SIZE: usize = 20;
const UDP_HEADER_SIZE: usize = 8;

/// Converts the path MTU to an uTP packet size.
pub(crate) fn to_packet_size(path_mtu: usize) -> usize {
    path_mtu - IP_HEADER_SIZE - UDP_HEADER_SIZE
}

/// Converts the path MTU to an ICMP payload size.
fn to_payload_size(path_mtu: usize) -> usize {
    path_mtu - IP_HEADER_SIZE - IcmpEchoHeader::SIZE
}

impl PathMtuProber {
    pub(crate) fn spawn() -> Result<(Self, PathMtuProberGuard), Error> {
        let socket = IcmpSocket::new()?;
        socket.set_mtu_discover(IpPmtudisc::Probe)?;
        socket.set_recverr(true)?;
        let (probe_send, probe_recv) = mpsc::channel(*crate::path_mtu_queue_size());
        let (path_mtu_send, path_mtu_recv) = mpsc::channel(*crate::path_mtu_queue_size());
        Ok((
            Self {
                probe_send,
                path_mtu_recv,
            },
            JoinGuard::spawn(move |cancel| {
                Actor::new(cancel, socket, probe_recv, path_mtu_send).run()
            }),
        ))
    }
}

impl Actor {
    pub(crate) fn new(
        cancel: Cancel,
        socket: IcmpSocket,
        probe_recv: Receiver<SocketAddr>,
        path_mtu_send: Sender<(SocketAddr, usize)>,
    ) -> Self {
        Self {
            cancel,
            socket,
            probe_recv,
            path_mtu_send,
        }
    }

    async fn run(mut self) {
        loop {
            tokio::select! {
                () = self.cancel.wait() => break,
                peer_endpoint = self.probe_recv.recv() => {
                    let Some(peer_endpoint) = peer_endpoint else { break };
                    self.probe(peer_endpoint).await;
                }
            }
        }
    }

    #[tracing::instrument(name = "utp/mtu", skip(self))]
    async fn probe(&self, peer_endpoint: SocketAddr) {
        if peer_endpoint.is_ipv6() {
            tracing::warn!("probing ipv6 path mtu is not supported at the moment");
            return;
        }

        // TODO: Retry when probing fails.
        match probe(&self.socket, peer_endpoint).await {
            Ok(path_mtu) => {
                let _ = self.path_mtu_send.send((peer_endpoint, path_mtu)).await;
            }
            Err(error) => {
                if error.kind() == ErrorKind::TimedOut {
                    tracing::debug!(?error, "path mtu probe timeout");
                } else {
                    tracing::warn!(?error, "path mtu probe error");
                }
            }
        }
    }
}

async fn probe(socket: &IcmpSocket, peer_endpoint: SocketAddr) -> Result<usize, Error> {
    let address = match peer_endpoint.ip() {
        IpAddr::V4(address) => address,
        IpAddr::V6(_) => {
            std::unreachable!(
                "probing ipv6 path mtu is not supported at the moment: {:?}",
                peer_endpoint,
            );
        }
    };
    let mut path_mtu = *crate::path_mtu_max_probe_size();
    let mut have_recv_icmp_mtu_reply = false;
    let mut header = IcmpEchoHeader::new(peer_endpoint.port(), 0);
    let mut buffer = [0u8; 65536];
    loop {
        tracing::debug!(path_mtu, "probe");
        let payload = &mut buffer[0..to_payload_size(path_mtu)];
        payload.fill(0);
        header.seq += 1;
        header.update_checksum(payload);

        let is_ok = match socket.send_to(&header, payload, address).await {
            Ok(_) => true,
            Err(error) => {
                if error.raw_os_error() != Some(libc::EMSGSIZE) {
                    return Err(error);
                }
                false
            }
        };

        if is_ok {
            // Ignore echo reply for now.
            let _ = time::timeout(
                *crate::path_mtu_icmp_reply_timeout(),
                socket.recv_from(buffer.as_mut_slice()),
            )
            .await
            .map_err(|_| Error::new(ErrorKind::TimedOut, "icmp reply timeout"))??;
            break;
        } else {
            let (_, endpoint, error) = socket.next_error(buffer.as_mut_slice()).unwrap();
            match error {
                libc::sock_extended_err {
                    ee_origin: libc::SO_EE_ORIGIN_LOCAL,
                    ee_type: 0,
                    ee_code: 0,
                    ..
                }
                | libc::sock_extended_err {
                    ee_origin: libc::SO_EE_ORIGIN_ICMP,
                    ee_type: 3,
                    ee_code: 4,
                    ..
                } if error.ee_errno == u32::try_from(libc::EMSGSIZE).unwrap() => {
                    path_mtu = error.ee_info.try_into().unwrap();
                    have_recv_icmp_mtu_reply = true;
                }
                _ => {
                    return Err(Error::other(format!(
                        "unexpected sock_extended_err: {:?} {:?}",
                        endpoint, error,
                    )));
                }
            }
        }
    }
    if have_recv_icmp_mtu_reply {
        tracing::debug!(path_mtu, "discover");
    } else {
        tracing::info!("path mtu >= max probe size");
    }
    Ok(path_mtu)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_size_conversion() {
        assert_eq!(to_packet_size(1000), 972);
        assert_eq!(to_payload_size(1000), 972);
    }
}
