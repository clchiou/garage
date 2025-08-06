use std::io::{self, Error, Read};
use std::net::SocketAddr;
use std::sync::Arc;

use bytes::Bytes;
use clap::Parser;
use tokio::net::UdpSocket;
use tokio::signal;

use g1_cli::tracing::TracingConfig;
use g1_msg::reqrep::{Protocol, ReqRep};

#[derive(Debug, Parser)]
struct UdpEcho {
    #[command(flatten)]
    tracing: TracingConfig,

    #[arg(long, short)]
    listen: bool,
    #[arg(default_value = "127.0.0.1:8000")]
    endpoint: SocketAddr,
}

struct UdpEchoProtocol;

impl Protocol for UdpEchoProtocol {
    type Id = SocketAddr;
    type Incoming = (SocketAddr, Bytes);
    type Outgoing = (SocketAddr, Bytes);

    type Error = Error;

    fn incoming_id((id, _): &Self::Incoming) -> Self::Id {
        *id
    }

    fn outgoing_id((id, _): &Self::Outgoing) -> Self::Id {
        *id
    }
}

impl UdpEcho {
    async fn execute(&self) -> Result<(), Error> {
        let socket = if self.listen {
            UdpSocket::bind(self.endpoint).await
        } else {
            UdpSocket::bind("0.0.0.0:0").await
        }?;

        eprintln!("self endpoint: {}", socket.local_addr()?);
        let (stream, sink) = g1_udp::split(Arc::new(socket));
        let (reqrep, mut guard) = ReqRep::<UdpEchoProtocol>::spawn(stream, sink);

        if self.listen {
            tokio::select! {
                result = signal::ctrl_c() => {
                    result?;
                    eprintln!("ctrl-c received!");
                }
                () = async {
                    while let Some(((endpoint, payload), response_send)) = reqrep.accept().await {
                        eprintln!("{} -> \"{}\"", endpoint, payload.escape_ascii());
                        response_send.send((endpoint, payload)).await;
                    }
                } => {}
            };
        } else {
            let mut payload = Vec::new();
            io::stdin().read_to_end(&mut payload)?;
            let response = reqrep
                .request((self.endpoint, payload.into()))
                .await
                .ok_or_else(|| Error::other("reqrep exit"))?;
            let (endpoint, response) = response.await.map_err(Error::other)?;
            eprintln!("{} -> \"{}\"", endpoint, response.escape_ascii());
        }

        guard.shutdown().await?
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let udp_echo = UdpEcho::parse();
    udp_echo.tracing.init();
    udp_echo.execute().await
}
