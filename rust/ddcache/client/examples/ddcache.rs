use std::fs::OpenOptions;
use std::io::Error;
use std::path::PathBuf;

use bytes::Bytes;
use clap::{Args, Parser, Subcommand};

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};

use ddcache_client::{Client, ClientGuard};
use ddcache_rpc::{Endpoint, Token};

#[derive(Debug, Parser)]
struct Program {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    // For some reason, global arguments cannot be required.
    #[arg(long)]
    endpoint: Vec<Endpoint>,

    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Ping,
    Read(Read),
    ReadMetadata(ReadMetadata),
    Write(Write),
    Cancel(Cancel),
}

#[derive(Args, Debug)]
struct Read {
    key: Bytes,
    file: PathBuf,
}

#[derive(Args, Debug)]
struct ReadMetadata {
    key: Bytes,
}

#[derive(Args, Debug)]
struct Write {
    #[arg(long)]
    write_any: bool,

    key: Bytes,
    #[arg(long)]
    metadata: Option<Bytes>,
    file: PathBuf,
}

#[derive(Args, Debug)]
struct Cancel {
    token: Token,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        let (client, mut guard) = self.connect().await?;
        match &self.command {
            Command::Ping => self.ping(client).await?,
            Command::Read(read) => Self::read(client, read).await?,
            Command::ReadMetadata(read_metadata) => {
                Self::read_metadata(client, read_metadata).await?
            }
            Command::Write(write) => Self::write(client, write).await?,
            Command::Cancel(cancel) => self.cancel(client, cancel).await?,
        }
        guard.shutdown().await?.map_err(Error::other)
    }

    async fn connect(&self) -> Result<(Client, ClientGuard), Error> {
        let (mut client, guard) = Client::spawn();
        for endpoint in self.endpoint.iter().cloned() {
            client.connect(endpoint).await.map_err(Error::other)?;
        }
        if self.endpoint.is_empty() && !client.service_ready().await {
            return Err(Error::other("service unavailable"));
        }
        Ok((client, guard))
    }

    async fn ping(&self, client: Client) -> Result<(), Error> {
        for endpoint in self.endpoint.iter().cloned() {
            client.ping(endpoint).await.map_err(Error::other)?;
        }
        Ok(())
    }

    async fn read(client: Client, read: &Read) -> Result<(), Error> {
        let mut file = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&read.file)?;
        let metadata = client
            .read(read.key.clone(), &mut file, None)
            .await
            .map_err(Error::other)?;
        eprintln!("read: blob={:?}", metadata);
        Ok(())
    }

    async fn read_metadata(client: Client, read_metadata: &ReadMetadata) -> Result<(), Error> {
        let metadata = client
            .read_metadata(read_metadata.key.clone())
            .await
            .map_err(Error::other)?;
        eprintln!("read_metadata: blob={:?}", metadata);
        Ok(())
    }

    async fn write(client: Client, write: &Write) -> Result<(), Error> {
        let mut file = OpenOptions::new().read(true).open(&write.file)?;
        let size = usize::try_from(file.metadata()?.len()).unwrap();
        let written = if write.write_any {
            client
                .write_any(write.key.clone(), write.metadata.clone(), &mut file, size)
                .await
        } else {
            client
                .write_all(write.key.clone(), write.metadata.clone(), &mut file, size)
                .await
        }
        .map_err(Error::other)?;
        eprintln!("write: {}", written);
        Ok(())
    }

    async fn cancel(&self, client: Client, cancel: &Cancel) -> Result<(), Error> {
        for endpoint in self.endpoint.iter().cloned() {
            client
                .cancel(endpoint, cancel.token)
                .await
                .map_err(Error::other)?;
        }
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
