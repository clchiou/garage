use std::io::{self, Error, Read};
use std::net::SocketAddr;

use clap::Parser;
use tokio::net;

use g1_base::fmt::EscapeAscii;
use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_msg::reqrep::ReqRep;
use g1_tokio::net::udp::UdpSocket;

#[derive(Debug, Parser)]
struct UdpEcho {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    #[arg(long, short)]
    listen: bool,
    #[arg(default_value = "127.0.0.1:8000")]
    endpoint: SocketAddr,
}

impl UdpEcho {
    async fn execute(&self) -> Result<(), Error> {
        let socket = if self.listen {
            UdpSocket::new(net::UdpSocket::bind(self.endpoint).await?)
        } else {
            UdpSocket::new(net::UdpSocket::bind("0.0.0.0:0").await?)
        };

        eprintln!("self endpoint: {}", socket.socket().local_addr()?);
        let (stream, sink) = socket.into_split();
        let reqrep = ReqRep::new(stream, sink);

        if self.listen {
            while let Some(((endpoint, payload), response_send)) = reqrep.accept().await {
                eprintln!("peer-> {} {:?}", endpoint, EscapeAscii(payload.as_ref()));
                if payload.as_ref() == b"exit\n" {
                    reqrep.close();
                }
                response_send.send((endpoint, payload)).await?;
            }
        } else {
            let mut payload = Vec::new();
            io::stdin().read_to_end(&mut payload)?;
            let (endpoint, response) = reqrep.request((self.endpoint, payload.into())).await?;
            eprintln!("peer-> {} {:?}", endpoint, EscapeAscii(response.as_ref()));
        }

        reqrep.shutdown().await
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let udp_echo = UdpEcho::parse();
    udp_echo.tracing.init();
    udp_echo.parameters.init();
    udp_echo.execute().await
}