use std::io::Error;
use std::net::SocketAddr;
use std::sync::Arc;

use clap::Parser;
use tokio::net::UdpSocket;
use tokio::signal;

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};

use bt_base::NodeId;
use bt_dht_node::Node;
use bt_peer::Peers;

#[derive(Debug, Parser)]
#[command(version = g1_cli::version!(), after_help = ParametersConfig::render())]
struct Dhtd {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,
}

g1_param::define!(self_id: NodeId = rand::random());
g1_param::define!(self_endpoint: SocketAddr = "0.0.0.0:6881".parse().expect("self_endpoint"));

g1_param::define!(bootstrap: Vec<String> = Default::default());

impl Dhtd {
    async fn execute(&self) -> Result<(), Error> {
        let self_id = self_id().clone();
        tracing::info!(%self_id);

        let socket = UdpSocket::bind(*self_endpoint()).await?;
        tracing::info!(self_endpoint = %socket.local_addr()?);
        let (stream, sink) = g1_udp::split(Arc::new(socket));

        let bootstrap = bootstrap().clone();
        if bootstrap.is_empty() {
            tracing::warn!("empty bootstrap list");
        }

        let (node, mut guard) = Node::spawn(self_id, Peers::new(), bootstrap.into(), stream, sink);

        tokio::spawn(async move { node.bootstrap().await });

        tokio::select! {
            result = signal::ctrl_c() => {
                result?;
                tracing::info!("ctrl-c received!");
            }
            () = &mut guard => {}
        }

        guard.shutdown().await?
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let dhtd = Dhtd::parse();
    dhtd.tracing.init();
    dhtd.parameters.init();
    dhtd.execute().await
}
