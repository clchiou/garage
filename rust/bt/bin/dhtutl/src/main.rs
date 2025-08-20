#![feature(iterator_try_collect)]

mod client;
mod lookup;
mod net;
mod reqrep;

use std::io::Error;
use std::net::SocketAddrV4;
use std::time::Duration;

use clap::{Args, Parser, Subcommand};
use tokio::net::UdpSocket;

use g1_cli::tracing::TracingConfig;

use bt_base::NodeId;

use crate::client::Client;
use crate::lookup::{LookupNodesCommand, LookupPeersCommand};
use crate::reqrep::{AnnouncePeerCommand, FindNodeCommand, GetPeersCommand, PingCommand};

//
// TODO: Support IPv6.
//

#[derive(Debug, Parser)]
#[command(version = g1_cli::version!())]
struct Dhtutl {
    #[command(flatten, next_display_order = 100)]
    tracing: TracingConfig,

    #[command(flatten, next_display_order = 0)]
    node: Node,

    // TODO: I am not sure why, but setting `next_display_order` here does not work.
    #[command(subcommand)]
    command: Command,
}

#[derive(Args, Debug)]
struct Node {
    #[arg(long, global = true, value_name = "ID", help = "Node id")]
    self_id: Option<NodeId>,

    #[arg(
        long,
        global = true,
        default_value = "0.0.0.0:0",
        value_name = "ENDPOINT",
        help = "Node endpoint"
    )]
    self_endpoint: SocketAddrV4,

    #[arg(
        long,
        global = true,
        default_value_t = 8,
        value_name = "SECOND",
        help = "Timeout for the response"
    )]
    recv_timeout: u64,
}

#[derive(Debug, Subcommand)]
enum Command {
    Ping(PingCommand),
    FindNode(FindNodeCommand),
    GetPeers(GetPeersCommand),
    AnnouncePeer(AnnouncePeerCommand),
    LookupNodes(LookupNodesCommand),
    LookupPeers(LookupPeersCommand),
}

impl Dhtutl {
    async fn execute(self) -> Result<(), Error> {
        let socket = UdpSocket::bind(self.node.self_endpoint).await?;
        tracing::debug!(self_endpoint = %socket.local_addr()?);
        self.command
            .run(
                self.node.self_id.clone().unwrap_or_else(rand::random),
                Client::new(socket, Duration::from_secs(self.node.recv_timeout)),
            )
            .await
    }
}

impl Command {
    async fn run(self, self_id: NodeId, client: Client) -> Result<(), Error> {
        match self {
            Self::Ping(command) => command.run(self_id, client).await,
            Self::FindNode(command) => command.run(self_id, client).await,
            Self::GetPeers(command) => command.run(self_id, client).await,
            Self::AnnouncePeer(command) => command.run(self_id, client).await,
            Self::LookupNodes(command) => command.run(self_id, client).await,
            Self::LookupPeers(command) => command.run(self_id, client).await,
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let dhtutl = Dhtutl::parse();
    dhtutl.tracing.init();
    dhtutl.execute().await
}
