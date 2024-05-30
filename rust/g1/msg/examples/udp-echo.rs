use std::io::{self, Error, Read};
use std::net::SocketAddr;

use clap::Parser;
use futures::future::FutureExt;
use tokio::net;
use tokio::signal;

use g1_base::fmt::EscapeAscii;
use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_msg::reqrep::ReqRep;
use g1_tokio::net::udp::UdpSocket;

#[derive(Debug, Parser)]
#[command(after_help = ParametersConfig::render())]
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
        let (reqrep, mut guard) = ReqRep::spawn(stream, sink);

        if self.listen {
            tokio::select! {
                () = signal::ctrl_c().map(Result::unwrap) => eprintln!("ctrl-c received!"),
                result = async {
                    while let Some(((endpoint, payload), response_send)) = reqrep.accept().await {
                        eprintln!("peer-> {} {:?}", endpoint, EscapeAscii(payload.as_ref()));
                        response_send.send((endpoint, payload)).await?;
                    }
                    Ok::<_, Error>(())
                } => result?,
            };
        } else {
            let mut payload = Vec::new();
            io::stdin().read_to_end(&mut payload)?;
            let (endpoint, response) = reqrep.request((self.endpoint, payload.into())).await?;
            eprintln!("peer-> {} {:?}", endpoint, EscapeAscii(response.as_ref()));
        }

        guard.shutdown().await?
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let udp_echo = UdpEcho::parse();
    udp_echo.tracing.init();
    udp_echo.parameters.init();
    udp_echo.execute().await
}
