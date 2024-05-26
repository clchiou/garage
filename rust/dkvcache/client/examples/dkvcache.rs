use std::io::Error;
use std::time::Duration;

use bytes::Bytes;
use clap::{Args, Parser, Subcommand};

use tokio::time;

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};

use dkvcache_client::Client;
use dkvcache_rpc::service;
use dkvcache_rpc::Timestamp;

#[derive(Debug, Parser)]
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
    Get(Get),
    Set(Set),
    Update(Update),
    Remove(Remove),
}

#[derive(Args, Debug)]
struct Get {
    key: Bytes,
}

#[derive(Args, Debug)]
struct Set {
    key: Bytes,
    value: Bytes,
    #[arg(long)]
    expire_at: Option<Timestamp>,
}

#[derive(Args, Debug)]
struct Update {
    key: Bytes,
    #[arg(long)]
    value: Option<Bytes>,
    #[arg(long)]
    expire_at: Option<Option<Timestamp>>,
}

#[derive(Args, Debug)]
struct Remove {
    key: Bytes,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        let (client, mut guard) = Client::spawn(service::pubsub())
            .await
            .map_err(Error::other)?;

        {
            let client = client.clone();
            match &self.command {
                Command::Get(get) => Self::get(client, get).await?,
                Command::Set(set) => Self::set(client, set).await?,
                Command::Update(update) => Self::update(client, update).await?,
                Command::Remove(remove) => Self::remove(client, remove).await?,
            }
        }

        // Give background tasks some time to finish.
        time::sleep(Duration::from_millis(50)).await;
        drop(client);

        guard.shutdown().await?.map_err(Error::other)
    }

    async fn get(client: Client, get: &Get) -> Result<(), Error> {
        let entry = client.get(get.key.clone()).await.map_err(Error::other)?;
        eprintln!("get: {:?}", entry);
        Ok(())
    }

    async fn set(client: Client, set: &Set) -> Result<(), Error> {
        let is_new = client
            .set(set.key.clone(), set.value.clone(), set.expire_at)
            .await
            .map_err(Error::other)?;
        eprintln!("set: {}", is_new);
        Ok(())
    }

    async fn update(client: Client, update: &Update) -> Result<(), Error> {
        let updated = client
            .update(update.key.clone(), update.value.clone(), update.expire_at)
            .await
            .map_err(Error::other)?;
        eprintln!("update: {}", updated);
        Ok(())
    }

    async fn remove(client: Client, remove: &Remove) -> Result<(), Error> {
        let removed = client
            .remove(remove.key.clone())
            .await
            .map_err(Error::other)?;
        eprintln!("remove: {}", removed);
        Ok(())
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let program = Program::parse();
    program.tracing.init();
    program.parameters.init();
    program.execute().await
}
