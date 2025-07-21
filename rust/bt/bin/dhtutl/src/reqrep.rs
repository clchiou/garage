use std::any;
use std::fmt;
use std::io::{self, Error, Write};

use clap::{Args, ValueEnum};

use g1_base::slice::ByteSliceExt;

use bt_base::{InfoHash, NodeId};
use bt_dht_proto::{
    AnnouncePeerResponse, FindNodeResponse, GetPeersResponse, Message, Payload, PingResponse,
    Query, Response, Token,
};

use crate::client::Client;
use crate::net;

#[derive(Args, Debug)]
struct ReqRepCommand {
    node_endpoint: String,
    #[arg(long, default_value_t = Format::Debug, value_enum)]
    format: Format,
}

#[derive(Clone, Debug, ValueEnum)]
enum Format {
    Bencode,
    Debug,
}

#[derive(Args, Debug)]
pub(crate) struct PingCommand {
    #[command(flatten)]
    command: ReqRepCommand,
}

#[derive(Args, Debug)]
pub(crate) struct FindNodeCommand {
    #[command(flatten)]
    command: ReqRepCommand,

    target: NodeId,
}

#[derive(Args, Debug)]
pub(crate) struct GetPeersCommand {
    #[command(flatten)]
    command: ReqRepCommand,

    info_hash: InfoHash,
}

#[derive(Args, Debug)]
pub(crate) struct AnnouncePeerCommand {
    #[command(flatten)]
    command: ReqRepCommand,

    #[arg(long)]
    implied_port: Option<bool>,
    info_hash: InfoHash,
    port: u16,
    token: String,
}

impl ReqRepCommand {
    async fn run<R>(self, client: Client, query: Message) -> Result<(), Error>
    where
        R: TryFrom<Response>,
        R: fmt::Debug,
        R::Error: fmt::Debug,
    {
        let (raw_response, response) = client
            .request(net::lookup_host_first(&self.node_endpoint).await?, query)
            .await?;

        if let Some(requestor) = &response.ip {
            tracing::debug!(%requestor);
        }

        let mut writer = io::stdout();
        match self.format {
            Format::Bencode => writer.write_all(&raw_response),
            Format::Debug => {
                let response: Box<dyn fmt::Debug> = match response.payload {
                    Payload::Query(_) => unreachable!(),
                    Payload::Response(response) => {
                        Box::new(R::try_from(response).map_err(|error| {
                            Error::other(format!("invalid {}: {:?}", any::type_name::<R>(), error))
                        })?)
                    }
                    Payload::Error(error) => Box::new(error),
                };

                writeln!(writer, "{response:#?}")
            }
        }
    }
}

impl PingCommand {
    pub(crate) async fn run(self, self_id: NodeId, client: Client) -> Result<(), Error> {
        self.command
            .run::<PingResponse>(client, Query::ping(self_id))
            .await
    }
}

impl FindNodeCommand {
    pub(crate) async fn run(self, self_id: NodeId, client: Client) -> Result<(), Error> {
        self.command
            .run::<FindNodeResponse>(client, Query::find_node(self_id, self.target))
            .await
    }
}

impl GetPeersCommand {
    pub(crate) async fn run(self, self_id: NodeId, client: Client) -> Result<(), Error> {
        self.command
            .run::<GetPeersResponse>(client, Query::get_peers(self_id, self.info_hash))
            .await
    }
}

impl AnnouncePeerCommand {
    pub(crate) async fn run(self, self_id: NodeId, client: Client) -> Result<(), Error> {
        self.command
            .run::<AnnouncePeerResponse>(
                client,
                Query::announce_peer(
                    self_id,
                    self.implied_port,
                    self.info_hash,
                    self.port,
                    unescape_ascii(&self.token)?,
                ),
            )
            .await
    }
}

fn unescape_ascii(escaped: &str) -> Result<Token, Error> {
    escaped
        .as_bytes()
        .unescape_ascii()
        .try_collect()
        .map_err(Error::other)
}
