#![feature(io_error_other)]

use std::future;
use std::io::Error;
use std::net::SocketAddr;
use std::sync::Arc;

use clap::{Args, Parser, Subcommand};
use tokio::net;

use g1_base::str::Hex;
use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_tokio::net::udp::UdpSocket;

use bittorrent_base::InfoHash;
use bittorrent_dht::{Agent, NodeId};

#[derive(Debug, Parser)]
struct Dht {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    #[arg(long, global = true, default_value = "0.0.0.0:6881")]
    self_endpoint: SocketAddr,
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Ping(Ping),
    FindNode(FindNode),
    GetPeers(GetPeers),
    AnnouncePeer(AnnouncePeer),
    LookupNodes(LookupNodes),
    LookupPeers(LookupPeers),
    Serve,
}

impl Dht {
    async fn execute(&self) -> Result<(), Error> {
        let socket = UdpSocket::new(net::UdpSocket::bind(self.self_endpoint).await?);
        let self_endpoint = socket.socket().local_addr()?;
        let (stream, sink) = socket.into_split();
        let agent = Agent::new_default(self_endpoint, stream, sink);
        match &self.command {
            Command::Ping(this) => this.execute(&agent).await?,
            Command::FindNode(this) => this.execute(&agent).await?,
            Command::GetPeers(this) => this.execute(&agent).await?,
            Command::AnnouncePeer(this) => this.execute(&agent).await?,
            Command::LookupNodes(this) => this.execute(&agent).await?,
            Command::LookupPeers(this) => this.execute(&agent).await?,
            Command::Serve => future::pending().await,
        }
        agent.shutdown().await
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let dht = Dht::parse();
    dht.tracing.init();
    dht.parameters.init();
    dht.execute().await
}

#[derive(Args, Debug)]
struct Ping {
    #[arg(long, default_value = "127.0.0.1:6881")]
    peer_endpoint: SocketAddr,
}

impl Ping {
    async fn execute(&self, agent: &Agent) -> Result<(), Error> {
        agent.ping(self.peer_endpoint).await
    }
}

#[derive(Args, Debug)]
struct FindNode {
    #[arg(long, default_value = "127.0.0.1:6881")]
    peer_endpoint: SocketAddr,

    #[arg(value_parser = parse_node_id)]
    target: NodeId,
}

impl FindNode {
    async fn execute(&self, agent: &Agent) -> Result<(), Error> {
        let nodes = agent
            .find_node(self.peer_endpoint, self.target.as_ref())
            .await?;
        println!("{:#?}", nodes);
        Ok(())
    }
}

#[derive(Args, Debug)]
struct GetPeers {
    #[arg(long, default_value = "127.0.0.1:6881")]
    peer_endpoint: SocketAddr,

    #[arg(value_parser = parse_info_hash)]
    info_hash: InfoHash,
}

impl GetPeers {
    async fn execute(&self, agent: &Agent) -> Result<(), Error> {
        use g1_base::fmt::Hex;
        let (token, peers, nodes) = agent
            .get_peers(self.peer_endpoint, self.info_hash.as_ref())
            .await?;
        println!(
            "{:#?}",
            (
                token.as_ref().map(|token| Hex(token.as_ref())),
                peers,
                nodes,
            ),
        );
        Ok(())
    }
}

#[derive(Args, Debug)]
struct AnnouncePeer {
    #[arg(long, default_value = "127.0.0.1:6881")]
    peer_endpoint: SocketAddr,

    #[arg(value_parser = parse_info_hash)]
    info_hash: InfoHash,
    port: u16,
    #[arg(long)]
    implied_port: Option<bool>,
    #[arg(value_parser = parse_token)]
    token: Arc<[u8]>,
}

impl AnnouncePeer {
    async fn execute(&self, agent: &Agent) -> Result<(), Error> {
        agent
            .announce_peer(
                self.peer_endpoint,
                self.info_hash.as_ref(),
                self.port,
                self.implied_port,
                &self.token,
            )
            .await
    }
}

#[derive(Args, Debug)]
struct LookupNodes {
    #[arg(value_parser = parse_node_id)]
    id: NodeId,
}

impl LookupNodes {
    async fn execute(&self, agent: &Agent) -> Result<(), Error> {
        println!("{:#?}", agent.lookup_nodes(self.id.clone()).await);
        Ok(())
    }
}

#[derive(Args, Debug)]
struct LookupPeers {
    #[arg(value_parser = parse_info_hash)]
    info_hash: InfoHash,
}

impl LookupPeers {
    async fn execute(&self, agent: &Agent) -> Result<(), Error> {
        use g1_base::fmt::Hex;
        let (peers, closest) = agent.lookup_peers(self.info_hash.clone()).await;
        println!(
            "{:#?}",
            (
                peers,
                closest
                    .as_ref()
                    .map(|(node, token)| (node, Hex(token.as_ref()))),
            ),
        );
        Ok(())
    }
}

fn parse_node_id(hex: &str) -> Result<NodeId, Error> {
    Ok(NodeId::new(
        Hex::try_from(hex)
            .map_err(|hex| Error::other(format!("invalid node id: {:?}", hex)))?
            .into_inner(),
    ))
}

fn parse_info_hash(hex: &str) -> Result<InfoHash, Error> {
    Ok(InfoHash::new(
        Hex::try_from(hex)
            .map_err(|hex| Error::other(format!("invalid info hash: {:?}", hex)))?
            .into_inner(),
    ))
}

fn parse_token(hex: &str) -> Result<Arc<[u8]>, Error> {
    let token: Hex<Vec<u8>> = hex
        .parse()
        .map_err(|_| Error::other(format!("invalid token: {:?}", hex)))?;
    Ok(token.into_inner().into())
}
