#![feature(try_blocks)]

use std::fs::OpenOptions;
use std::io;
use std::path::PathBuf;
use std::time::Duration;

use bytes::Bytes;
use capnp::message;
use capnp::serialize;
use clap::{Args, Parser, Subcommand};
use tokio::time;
use zmq::{Context, REP};

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_zmq::Socket;

use ddcache_client_raw::{Error, RawNaiveClient};
use ddcache_rpc::{Endpoint, RequestOwner, ResponseBuilder, Timestamp, Token};

#[derive(Debug, Parser)]
struct Program {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    // For some reason, global arguments cannot be required.
    #[arg(long)]
    endpoint: Endpoint,

    #[arg(long, global = true, default_value = "0")]
    delay: u64,

    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Cancel(Cancel),
    Read(Read),
    ReadMetadata(ReadMetadata),
    Write(Write),
    WriteMetadata(WriteMetadata),
    Remove(Remove),

    Pull(Pull),
    Push(Push),

    Dummy,
}

#[derive(Args, Debug)]
struct Cancel {
    token: Token,
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

#[derive(Args, Debug)]
struct Pull {
    key: Bytes,
    file: PathBuf,
}

#[derive(Args, Debug)]
struct Push {
    key: Bytes,
    #[arg(long)]
    metadata: Option<Bytes>,
    #[arg(long)]
    expire_at: Option<Timestamp>,
    file: PathBuf,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        match &self.command {
            Command::Cancel(cancel) => self.cancel(cancel).await?,
            Command::Read(read) => self.read(read).await?,
            Command::ReadMetadata(read_metadata) => self.read_metadata(read_metadata).await?,
            Command::Write(write) => self.write(write).await?,
            Command::WriteMetadata(write_metadata) => self.write_metadata(write_metadata).await?,
            Command::Remove(remove) => self.remove(remove).await?,

            Command::Pull(pull) => self.pull(pull).await?,
            Command::Push(push) => self.push(push).await?,

            Command::Dummy => self.dummy().await.unwrap(),
        }
        Ok(())
    }

    async fn cancel(&self, cancel: &Cancel) -> Result<(), Error> {
        let response = RawNaiveClient::connect(self.endpoint.clone())?
            .cancel(cancel.token)
            .await?;
        eprintln!("cancel: {:?}", response);
        Ok(())
    }

    async fn read(&self, read: &Read) -> Result<(), Error> {
        let response = RawNaiveClient::connect(self.endpoint.clone())?
            .read(read.key.clone())
            .await?;
        eprintln!("read: {:?}", response);

        if self.delay > 0 {
            time::sleep(Duration::from_secs(self.delay)).await;
        }

        let mut output = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&read.file)
            .unwrap();

        let response = response.unwrap();
        let metadata = response.metadata.unwrap();
        let blob = response.blob.unwrap();
        blob.read(&mut output, metadata.size).await
    }

    async fn read_metadata(&self, read_metadata: &ReadMetadata) -> Result<(), Error> {
        let response = RawNaiveClient::connect(self.endpoint.clone())?
            .read_metadata(read_metadata.key.clone())
            .await?;
        eprintln!("read_metadata: {:?}", response);
        Ok(())
    }

    async fn write(&self, write: &Write) -> Result<(), Error> {
        let mut input = OpenOptions::new().read(true).open(&write.file).unwrap();
        let size = usize::try_from(input.metadata().unwrap().len()).unwrap();

        let response = RawNaiveClient::connect(self.endpoint.clone())?
            .write(
                write.key.clone(),
                write.metadata.clone(),
                size,
                write.expire_at,
            )
            .await?;
        eprintln!("write: {:?}", response);

        if self.delay > 0 {
            time::sleep(Duration::from_secs(self.delay)).await;
        }

        response
            .unwrap()
            .blob
            .unwrap()
            .write_file(&mut input, None, size)
            .await
    }

    async fn write_metadata(&self, write_metadata: &WriteMetadata) -> Result<(), Error> {
        let response = RawNaiveClient::connect(self.endpoint.clone())?
            .write_metadata(
                write_metadata.key.clone(),
                write_metadata.metadata.clone(),
                write_metadata.expire_at.clone(),
            )
            .await?;
        eprintln!("write_metadata: {:?}", response);
        Ok(())
    }

    async fn remove(&self, remove: &Remove) -> Result<(), Error> {
        let response = RawNaiveClient::connect(self.endpoint.clone())?
            .remove(remove.key.clone())
            .await?;
        eprintln!("remove: {:?}", response);
        Ok(())
    }

    async fn pull(&self, pull: &Pull) -> Result<(), Error> {
        let response = RawNaiveClient::connect(self.endpoint.clone())?
            .pull(pull.key.clone())
            .await?;
        eprintln!("pull: {:?}", response);

        if self.delay > 0 {
            time::sleep(Duration::from_secs(self.delay)).await;
        }

        let mut output = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&pull.file)
            .unwrap();

        let response = response.unwrap();
        let metadata = response.metadata.unwrap();
        let blob = response.blob.unwrap();
        blob.read(&mut output, metadata.size).await
    }

    async fn push(&self, push: &Push) -> Result<(), Error> {
        let mut input = OpenOptions::new().read(true).open(&push.file).unwrap();
        let size = usize::try_from(input.metadata().unwrap().len()).unwrap();

        let response = RawNaiveClient::connect(self.endpoint.clone())?
            .push(
                push.key.clone(),
                push.metadata.clone(),
                size,
                push.expire_at,
            )
            .await?;
        eprintln!("push: {:?}", response);

        if self.delay > 0 {
            time::sleep(Duration::from_secs(self.delay)).await;
        }

        response
            .unwrap()
            .blob
            .unwrap()
            .write_file(&mut input, None, size)
            .await
    }

    async fn dummy(&self) -> Result<(), io::Error> {
        let mut socket = Socket::try_from(Context::new().socket(REP)?)?;
        socket.bind(&self.endpoint)?;
        loop {
            let request = socket.recv_msg(0).await?;
            let request = RequestOwner::try_from(request).map_err(io::Error::other)?;
            eprintln!("request: {:?}", &*request);

            let mut response = message::Builder::new_default();
            response
                .init_root::<ResponseBuilder>()
                .init_err()
                .set_server(());
            let response = serialize::write_message_to_words(&response);
            socket.send(response, 0).await?;
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let program = Program::parse();
    program.tracing.init();
    program.parameters.init();
    program.execute().await
}
