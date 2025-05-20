use std::marker::Unpin;
use std::ops::Bound;
use std::time::Duration;

use base64::DecodeError;
use base64::prelude::*;
use clap::{Args, Parser, Subcommand};
use futures::stream::{Stream, TryStreamExt};

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};

use etcd_client::request;
use etcd_client::{Auth, Client, ClientBuilder, Error, Event};

#[derive(Debug, Parser)]
#[command(after_help = ParametersConfig::render())]
struct Program {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Authenticate(Authenticate),
    Range(Range),
    RangePrefix(Key),
    Get(Key),
    Put(Put),
    Delete(Range),
    DeletePrefix(Key),
    DeleteKey(Key),
    Watch(Range),
    WatchPrefix(Key),
    WatchKey(Key),
    LeaseGrant(LeaseGrant),
    LeaseKeepAlive(LeaseId),
    LeaseRevoke(LeaseId),
}

#[derive(Args, Debug)]
struct Authenticate {
    name: String,
    password: String,
}

#[derive(Args, Debug)]
struct Range {
    #[arg(long)]
    base64: bool,

    #[arg(long)]
    start_open: bool,
    start: Option<String>,

    #[arg(long)]
    end_close: bool,
    end: Option<String>,
}

type RangeBounds = (Bound<etcd_client::Key>, Bound<etcd_client::Key>);

#[derive(Args, Debug)]
struct Key {
    #[arg(long)]
    base64: bool,

    key: String,
}

#[derive(Args, Debug)]
struct Put {
    #[arg(long)]
    lease: Option<i64>,

    #[arg(long)]
    base64: bool,

    key: String,
    value: String,
}

#[derive(Args, Debug)]
struct LeaseGrant {
    ttl: u64,
    id: Option<i64>,
}

#[derive(Args, Debug)]
struct LeaseId {
    id: i64,
}

impl Program {
    async fn execute(self) -> Result<(), Error> {
        match self.command {
            Command::Authenticate(auth) => {
                let client = ClientBuilder::new()
                    .auth(Some(Auth::Authenticate(request::Authenticate {
                        name: auth.name,
                        password: auth.password,
                    })))
                    .build();
                client.authenticate().await?;
                eprintln!("{:?}", client.auth_token());
            }
            Command::Range(range) => {
                let client = Client::new();
                let range = RangeBounds::try_from(range).unwrap();
                show_kvs(&client.range(range, None).await?)
            }
            Command::RangePrefix(key) => {
                let client = Client::new();
                let key = etcd_client::Key::try_from(key).unwrap();
                show_kvs(&client.range_prefix(key, None).await?);
            }
            Command::Get(key) => {
                let client = Client::new();
                let key = etcd_client::Key::try_from(key).unwrap();
                show_vs(client.get(key).await?.as_ref());
            }
            Command::Put(put) => {
                let client = Client::new();
                let lease = put.lease;
                let (key, value) = put.try_into().unwrap();
                show_kvs(client.put(key, value, lease).await?.as_ref());
            }
            Command::Delete(range) => {
                let client = Client::new();
                let range = RangeBounds::try_from(range).unwrap();
                eprintln!("delete: {}", client.delete(range).await?);
            }
            Command::DeletePrefix(key) => {
                let client = Client::new();
                let key = etcd_client::Key::try_from(key).unwrap();
                eprintln!("delete: {}", client.delete_prefix(key).await?);
            }
            Command::DeleteKey(key) => {
                let client = Client::new();
                let key = etcd_client::Key::try_from(key).unwrap();
                show_kvs(client.delete_key(key).await?.as_ref());
            }
            Command::Watch(range) => {
                let client = Client::new();
                let range = RangeBounds::try_from(range).unwrap();
                show_events(client.watch(range).await?).await?;
            }
            Command::WatchPrefix(key) => {
                let client = Client::new();
                let key = etcd_client::Key::try_from(key).unwrap();
                show_events(client.watch_prefix(key).await?).await?;
            }
            Command::WatchKey(key) => {
                let client = Client::new();
                let key = etcd_client::Key::try_from(key).unwrap();
                show_events(client.watch_key(key).await?).await?;
            }
            Command::LeaseGrant(grant) => {
                let client = Client::new();
                let id = client
                    .lease_grant(Duration::from_secs(grant.ttl), grant.id)
                    .await?;
                eprintln!("lease: id={}", id);
            }
            Command::LeaseKeepAlive(id) => {
                let client = Client::new();
                client.lease_keep_alive(id.id).await?;
            }
            Command::LeaseRevoke(id) => {
                let client = Client::new();
                client.lease_revoke(id.id).await?;
            }
        }
        Ok(())
    }
}

impl TryFrom<Range> for RangeBounds {
    type Error = DecodeError;

    fn try_from(range: Range) -> Result<Self, Self::Error> {
        fn to_key(
            key: Option<String>,
            base64: bool,
        ) -> Result<Option<etcd_client::Key>, DecodeError> {
            key.map(|key| decode(key, base64)).transpose()
        }

        fn to_bound(key: Option<etcd_client::Key>, open: bool) -> Bound<etcd_client::Key> {
            match key {
                Some(key) => {
                    if open {
                        Bound::Excluded(key)
                    } else {
                        Bound::Included(key)
                    }
                }
                None => Bound::Unbounded,
            }
        }

        Ok((
            to_bound(to_key(range.start, range.base64)?, range.start_open),
            to_bound(to_key(range.end, range.base64)?, !range.end_close),
        ))
    }
}

impl TryFrom<Key> for etcd_client::Key {
    type Error = DecodeError;

    fn try_from(key: Key) -> Result<Self, Self::Error> {
        decode(key.key, key.base64)
    }
}

impl TryFrom<Put> for (etcd_client::Key, etcd_client::Value) {
    type Error = DecodeError;

    fn try_from(put: Put) -> Result<Self, Self::Error> {
        Ok((decode(put.key, put.base64)?, decode(put.value, put.base64)?))
    }
}

fn decode(value: String, base64: bool) -> Result<Vec<u8>, DecodeError> {
    Ok(if base64 {
        BASE64_STANDARD.decode(value.as_bytes())?
    } else {
        value.into_bytes()
    })
}

fn show_kvs<'a>(kvs: impl IntoIterator<Item = &'a etcd_client::KeyValue>) {
    for kv in kvs {
        show_kv(kv);
    }
}

fn show_kv((k, v): &etcd_client::KeyValue) {
    eprintln!("\"{}\": \"{}\"", k.escape_ascii(), v.escape_ascii());
}

fn show_vs<'a>(vs: impl IntoIterator<Item = &'a etcd_client::Value>) {
    for v in vs {
        eprintln!("\"{}\"", v.escape_ascii());
    }
}

async fn show_events(
    mut events: impl Stream<Item = Result<Event, Error>> + Unpin,
) -> Result<(), Error> {
    while let Some(event) = events.try_next().await? {
        match event {
            Event::Create(kv) => {
                eprint!("create ");
                show_kv(&kv);
            }
            Event::Update { key, new, old } => eprintln!(
                "update \"{}\": \"{}\" -> \"{}\"",
                key.escape_ascii(),
                old.escape_ascii(),
                new.escape_ascii(),
            ),
            Event::Delete(kv) => {
                eprint!("delete ");
                show_kv(&kv);
            }
        }
    }
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let program = Program::parse();
    program.tracing.init();
    program.parameters.init();
    program.execute().await
}
