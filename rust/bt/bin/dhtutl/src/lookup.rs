use std::fmt;
use std::io::{self, Error, Write};
use std::net::SocketAddr;

use clap::Args;

use bt_base::{InfoHash, NodeId};
use bt_dht_lookup::{Lookup, Target};
use bt_dht_proto::{FindNodeResponse, NodeInfo, Payload, Query};

use crate::client::Client;
use crate::net;

#[derive(Args, Debug)]
struct LookupCommand {
    #[arg(
        short,
        long,
        value_name = "ENDPOINT",
        help = "Bootstrap lookup from these DHT routers"
    )]
    bootstrap: Vec<String>,
}

#[derive(Args, Debug)]
#[command(about = "Look up nodes in DHT", next_display_order = 10)]
pub(crate) struct LookupNodesCommand {
    #[command(flatten)]
    command: LookupCommand,

    target: NodeId,
}

#[derive(Args, Debug)]
#[command(about = "Look up peers in DHT", next_display_order = 10)]
pub(crate) struct LookupPeersCommand {
    #[command(flatten)]
    command: LookupCommand,

    info_hash: InfoHash,
}

impl LookupCommand {
    async fn run<T>(self, self_id: NodeId, client: Client, target: T) -> Result<(), Error>
    where
        T: Target,
        T::Output: fmt::Debug,
    {
        let bootstrap = self
            .bootstrap(self_id.clone(), &client, target.to_id())
            .await?;
        let mut lookup = Lookup::new(self_id, target, bootstrap);

        let mut queried = Vec::new();

        while let Some(queries) = lookup.next_iteration() {
            for (info, query) in queries {
                let endpoint = match info.endpoint {
                    SocketAddr::V4(endpoint) => endpoint,
                    SocketAddr::V6(endpoint) => panic!("ipv6 is not supported: {endpoint}"),
                };
                let response = match client.request(endpoint, query).await {
                    Ok((_, response)) => response,
                    Err(error) => {
                        tracing::warn!(%info, %error, "lookup request");
                        continue;
                    }
                };

                let response = match response.payload {
                    Payload::Query(_) => unreachable!(),
                    Payload::Response(response) => response,
                    Payload::Error(error) => {
                        tracing::warn!(%info, ?error, "lookup query");
                        continue;
                    }
                };

                if let Err(response) = lookup.update(info.clone(), response) {
                    tracing::warn!(%info, ?response, "lookup invalid");
                    continue;
                }

                queried.push(info);

                //
                // We skip the step of inserting into the routing table.
                //
            }
        }

        #[allow(dead_code)]
        #[derive(Debug)]
        struct Output<T> {
            queried: Vec<NodeInfo>,
            lookup: T,
        }

        let mut writer = io::stdout();
        writeln!(
            writer,
            "{:#?}",
            Output {
                queried,
                lookup: lookup.finish(),
            },
        )
    }

    async fn bootstrap(
        &self,
        self_id: NodeId,
        client: &Client,
        target: NodeId,
    ) -> Result<Vec<NodeInfo>, Error> {
        let mut infos = Vec::new();

        for endpoint in &self.bootstrap {
            let response = match client
                .request(
                    net::lookup_host_first(endpoint).await?,
                    Query::find_node(self_id.clone(), target.clone()),
                )
                .await
            {
                Ok((_, response)) => response,
                Err(error) => {
                    tracing::warn!(%error, "bootstrap request");
                    continue;
                }
            };

            let response = match response.payload {
                Payload::Query(_) => unreachable!(),
                Payload::Response(response) => response,
                Payload::Error(error) => {
                    tracing::warn!(?error, "bootstrap find_node");
                    continue;
                }
            };

            match response.try_into() {
                Ok(FindNodeResponse { nodes, .. }) => infos.extend(nodes),
                Err(response) => tracing::warn!(?response, "bootstrap invalid"),
            }
        }

        if infos.is_empty() {
            Err(Error::other("bootstrap empty"))
        } else {
            Ok(infos)
        }
    }
}

impl LookupNodesCommand {
    pub(crate) async fn run(self, self_id: NodeId, client: Client) -> Result<(), Error> {
        self.command.run(self_id, client, self.target).await
    }
}

impl LookupPeersCommand {
    pub(crate) async fn run(self, self_id: NodeId, client: Client) -> Result<(), Error> {
        self.command.run(self_id, client, self.info_hash).await
    }
}
