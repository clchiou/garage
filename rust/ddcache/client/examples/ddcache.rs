use std::fs::OpenOptions;
use std::io::Error;
use std::path::PathBuf;

use bytes::Bytes;
use clap::{Args, Parser, Subcommand};

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};

use ddcache_client::Client;
use ddcache_rpc::Timestamp;

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
    Read(Read),
    ReadMetadata(ReadMetadata),
    Write(Write),
    WriteMetadata(WriteMetadata),
    Remove(Remove),
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
    #[arg(long)]
    expire_at: Option<Timestamp>,
    file: PathBuf,
}

#[derive(Args, Debug)]
struct WriteMetadata {
    key: Bytes,
    #[arg(long)]
    metadata: Option<Option<Bytes>>,
    #[arg(long)]
    expire_at: Option<Option<Timestamp>>,
}

#[derive(Args, Debug)]
struct Remove {
    key: Bytes,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        let (client, mut guard) = Client::spawn();

        tokio::select! {
            () = client.service_ready() => {}
            () = guard.join() => return Err(Error::other("service unavailable")),
        }

        match &self.command {
            Command::Read(read) => Self::read(client, read).await?,
            Command::ReadMetadata(read_metadata) => {
                Self::read_metadata(client, read_metadata).await?
            }
            Command::Write(write) => Self::write(client, write).await?,
            Command::WriteMetadata(write_metadata) => {
                Self::write_metadata(client, write_metadata).await?
            }
            Command::Remove(remove) => Self::remove(client, remove).await?,
        }

        guard.shutdown().await?.map_err(Error::other)
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
                .write_any(
                    write.key.clone(),
                    write.metadata.clone(),
                    &mut file,
                    size,
                    write.expire_at,
                )
                .await
        } else {
            client
                .write_all(
                    write.key.clone(),
                    write.metadata.clone(),
                    &mut file,
                    size,
                    write.expire_at,
                )
                .await
        }
        .map_err(Error::other)?;
        eprintln!("write: {}", written);
        Ok(())
    }

    async fn write_metadata(client: Client, write_metadata: &WriteMetadata) -> Result<(), Error> {
        let written = client
            .write_metadata(
                write_metadata.key.clone(),
                write_metadata.metadata.clone(),
                write_metadata.expire_at,
            )
            .await
            .map_err(Error::other)?;
        eprintln!("write_metadata: {}", written);
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
