use std::io::Error;
use std::net::Ipv4Addr;

use clap::Parser;
use rand::prelude::*;

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_tokio::net::icmp::{IcmpEchoHeader, IcmpSocket, IpPmtudisc};

#[derive(Debug, Parser)]
#[command(after_help = ParametersConfig::render())]
struct PathMtu {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    address: Ipv4Addr,
}

const IP_HEADER_SIZE: usize = 20;

const MAX_PROBE_MTU: usize = 1600;

impl PathMtu {
    async fn execute(&self) -> Result<(), Error> {
        let socket = IcmpSocket::new()?;
        socket.set_mtu_discover(IpPmtudisc::Probe)?;
        socket.set_recverr(true)?;

        let mut probe_data = vec![0u8; to_payload_size(MAX_PROBE_MTU)];
        rand::rng().fill(probe_data.as_mut_slice());

        let mut path_mtu = MAX_PROBE_MTU;
        let mut have_recv_icmp_mtu_reply = false;
        let mut header = IcmpEchoHeader::new(rand::random(), 0);
        loop {
            tracing::info!(path_mtu, "probe");
            let payload = &probe_data[0..to_payload_size(path_mtu)];
            header.seq += 1;
            header.update_checksum(payload);

            let is_ok = match socket.send_to(&header, payload, self.address).await {
                Ok(_) => true,
                Err(error) => {
                    if error.raw_os_error() != Some(libc::EMSGSIZE) {
                        return Err(error);
                    }
                    false
                }
            };

            let mut buffer = [0u8; 65536];
            if is_ok {
                let (_, peer_endpoint) = socket.recv_from(buffer.as_mut_slice()).await?;
                tracing::info!(?peer_endpoint, "receive icmp reply");
                break; // Ignore echo reply.
            } else {
                let (num_bytes_recv, peer_endpoint, error) =
                    socket.next_error(buffer.as_mut_slice()).unwrap();
                tracing::info!(?peer_endpoint, "receive icmp error");
                assert_eq!(&buffer[..num_bytes_recv], &probe_data[..num_bytes_recv]);
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
                    _ => std::panic!("unexpected sock_extended_err: {:?}", error),
                }
            }
        }
        if have_recv_icmp_mtu_reply {
            tracing::info!(path_mtu, "discover");
        } else {
            tracing::info!(path_mtu_lower_bound = path_mtu, "discover");
        }

        Ok(())
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let prog = PathMtu::parse();
    prog.tracing.init();
    prog.parameters.init();
    prog.execute().await
}

fn to_payload_size(packet_size: usize) -> usize {
    packet_size - IP_HEADER_SIZE - IcmpEchoHeader::SIZE
}
