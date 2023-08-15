use std::collections::{hash_map::Entry, HashMap};
use std::io::{Error, ErrorKind};
use std::net::{IpAddr, SocketAddr};
use std::panic;
use std::sync::Arc;
use std::time::Duration;

use tokio::{
    task::JoinHandle,
    time::{self, Instant},
};
use tracing::Instrument;

use g1_tokio::net::icmp::{IcmpEchoHeader, IcmpSocket, IpPmtudisc};

// TODO: Support IPv6.
#[derive(Debug)]
pub(crate) struct PathMtuProber {
    socket: Arc<IcmpSocket>,
    last_probe_ats: HashMap<SocketAddr, Instant>,
    reprobe_after: Duration,
    probe_task: Option<(SocketAddr, JoinHandle<Result<usize, Error>>)>,
    next_probe_at: Option<(Instant, SocketAddr)>,
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
    pub(crate) fn new(reprobe_after: Duration) -> Result<Self, Error> {
        let socket = IcmpSocket::new()?;
        socket.set_mtu_discover(IpPmtudisc::Probe)?;
        socket.set_recverr(true)?;
        Ok(Self {
            socket: Arc::new(socket),
            last_probe_ats: HashMap::new(),
            reprobe_after,
            probe_task: None,
            next_probe_at: None,
        })
    }

    pub(crate) fn register(&mut self, peer_endpoint: SocketAddr) {
        if peer_endpoint.is_ipv6() {
            tracing::warn!(
                ?peer_endpoint,
                "probing ipv6 path mtu is not supported at the moment",
            );
            return;
        }
        if let Entry::Vacant(entry) = self.last_probe_ats.entry(peer_endpoint) {
            // Probe the new peer immediately.
            let new_next_probe_at = *entry.insert(Instant::now());
            if self
                .next_probe_at
                .map(|(next_probe_at, _)| new_next_probe_at < next_probe_at)
                .unwrap_or(true)
            {
                self.next_probe_at = Some((new_next_probe_at, peer_endpoint));
            }
        }
    }

    pub(crate) fn unregister(&mut self, peer_endpoint: &SocketAddr) {
        if peer_endpoint.is_ipv6() {
            tracing::warn!(
                ?peer_endpoint,
                "probing ipv6 path mtu is not supported at the moment",
            );
            return;
        }
        if self.last_probe_ats.remove(peer_endpoint).is_some()
            && self
                .next_probe_at
                .map(|(_, endpoint)| endpoint == *peer_endpoint)
                .unwrap_or(false)
        {
            self.next_probe_at = None;
        }
    }

    pub(crate) async fn next(&mut self) -> Option<(SocketAddr, usize)> {
        // NOTE: Be aware of cancellation safety.  As a general rule, you should only modify
        // `probe_task` or `next_probe_at` after a successful asynchronous operation.
        loop {
            if let Some((peer_endpoint, probe_task)) = self.probe_task.as_mut() {
                let mut path_mtu = match probe_task.await {
                    Ok(Ok(path_mtu)) => Some((*peer_endpoint, path_mtu)),
                    Ok(Err(error)) => {
                        tracing::warn!(?peer_endpoint, ?error, "path mtu probe error");
                        None
                    }
                    Err(join_error) => {
                        if join_error.is_panic() {
                            panic::resume_unwind(join_error.into_panic());
                        }
                        assert!(join_error.is_cancelled());
                        tracing::warn!(?peer_endpoint, "path mtu probe task is cancelled");
                        None
                    }
                };

                match self.last_probe_ats.get_mut(peer_endpoint) {
                    Some(last_probe_at) => {
                        *last_probe_at = Instant::now();
                    }
                    None => {
                        // Do not return the path MTU if the peer has been unregistered.
                        path_mtu = None;
                    }
                }

                self.probe_task = None;

                if path_mtu.is_some() {
                    return path_mtu;
                }
            }

            if self.next_probe_at.is_none() {
                let (peer_endpoint, last_probe_at) = self
                    .last_probe_ats
                    .iter()
                    .min_by_key(|(_, last_probe_at)| *last_probe_at)?;
                self.next_probe_at = Some((*last_probe_at + self.reprobe_after, *peer_endpoint));
            }

            let (probe_at, peer_endpoint) = self.next_probe_at.unwrap();
            time::sleep_until(probe_at).await;

            self.probe_task = Some((
                peer_endpoint,
                tokio::spawn(
                    probe(self.socket.clone(), peer_endpoint)
                        .instrument(tracing::info_span!("utp/mtu", ?peer_endpoint)),
                ),
            ));
            self.next_probe_at = None;
        }
    }
}

impl Drop for PathMtuProber {
    fn drop(&mut self) {
        if let Some((_, probe_task)) = self.probe_task.as_ref() {
            probe_task.abort();
        }
    }
}

async fn probe(socket: Arc<IcmpSocket>, peer_endpoint: SocketAddr) -> Result<usize, Error> {
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
