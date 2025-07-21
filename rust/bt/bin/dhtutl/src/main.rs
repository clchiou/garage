#![feature(iterator_try_collect)]

mod client;
mod lookup;
mod net;
mod reqrep;

use std::io::Error;
use std::net::SocketAddrV4;
use std::time::Duration;

use clap::{Parser, Subcommand};
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
    #[command(flatten)]
    tracing: TracingConfig,

    #[arg(long, global = true)]
    self_id: Option<NodeId>,

    #[arg(long, global = true, default_value = "0.0.0.0:0")]
    self_endpoint: SocketAddrV4,
    #[arg(long, global = true, default_value_t = 8)]
    recv_timeout: u64,

    #[command(subcommand)]
    command: Command,
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
        let socket = UdpSocket::bind(self.self_endpoint).await?;
        tracing::debug!(self_endpoint = %socket.local_addr()?);
        self.command
            .run(
                self.self_id.clone().unwrap_or_else(rand::random),
                Client::new(socket, Duration::from_secs(self.recv_timeout)),
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
