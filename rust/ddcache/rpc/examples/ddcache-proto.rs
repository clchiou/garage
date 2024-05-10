#![feature(try_blocks)]

use std::fs::OpenOptions;
use std::io::Error;
use std::path::PathBuf;
use std::time::Duration;

use bytes::Bytes;
use capnp::message;
use capnp::serialize;
use clap::{Args, Parser, Subcommand};
use tokio::io::AsyncWriteExt;
use tokio::net::TcpStream;
use tokio::time;
use zmq::{Context, Message, REP, REQ};

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_tokio::os::Splice;
use g1_zmq::Socket;

use ddcache_rpc::{
    Endpoint, Request, RequestOwner, Response, ResponseBuilder, ResponseOwner, ResponseResult,
    Timestamp, Token,
};

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

            Command::Dummy => self.dummy().await?,
        }
        Ok(())
    }

    fn make_socket(&self) -> Result<Socket, Error> {
        let mut socket = Socket::try_from(Context::new().socket(REQ)?)?;
        socket.connect(&self.endpoint)?;
        Ok(socket)
    }

    async fn cancel(&self, cancel: &Cancel) -> Result<(), Error> {
        let mut socket = self.make_socket()?;

        let request = encode(Request::Cancel(cancel.token));
        socket.send(request, 0).await?;

        let response = decode(socket.recv_msg(0).await?)?;
        eprintln!("cancel: {:?}", response);

        Ok(())
    }

    async fn read(&self, read: &Read) -> Result<(), Error> {
        let mut socket = self.make_socket()?;

        let request = encode(Request::Read {
            key: read.key.clone(),
        });
        socket.send(request, 0).await?;

        let response = decode(socket.recv_msg(0).await?)?;
        eprintln!("read: {:?}", response);

        let (metadata, blob) = match response {
            Some(Response::Read { metadata, blob }) => (metadata, blob),
            Some(_) => return Err(Error::other("wrong response")),
            None => return Ok(()),
        };

        if self.delay > 0 {
            time::sleep(Duration::from_secs(self.delay)).await;
        }

        let mut file = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&read.file)?;

        let mut blob_socket = TcpStream::connect(blob.endpoint).await?;
        blob_socket.write_u64(blob.token).await?;
        let size = blob_socket.splice(&mut file, metadata.size).await?;
        eprintln!("read: size={}", size);

        Ok(())
    }

    async fn read_metadata(&self, read_metadata: &ReadMetadata) -> Result<(), Error> {
        let mut socket = self.make_socket()?;

        let request = encode(Request::ReadMetadata {
            key: read_metadata.key.clone(),
        });
        socket.send(request, 0).await?;

        let response = decode(socket.recv_msg(0).await?)?;
        eprintln!("read_metadata: {:?}", response);

        Ok(())
    }

    async fn write(&self, write: &Write) -> Result<(), Error> {
        let mut file = OpenOptions::new().read(true).open(&write.file)?;
        let size = usize::try_from(file.metadata()?.len()).unwrap();

        let mut socket = self.make_socket()?;

        let request = encode(Request::Write {
            key: write.key.clone(),
            metadata: write.metadata.clone(),
            size,
            expire_at: write.expire_at,
        });
        socket.send(request, 0).await?;

        let response = decode(socket.recv_msg(0).await?)?;
        eprintln!("write: {:?}", response);

        let blob = match response {
            Some(Response::Write { blob }) => blob,
            Some(_) => return Err(Error::other("wrong response")),
            None => return Ok(()),
        };

        if self.delay > 0 {
            time::sleep(Duration::from_secs(self.delay)).await;
        }

        let mut blob_socket = TcpStream::connect(blob.endpoint).await?;
        blob_socket.write_u64(blob.token).await?;
        let size = file.splice(&mut blob_socket, size).await?;
        eprintln!("write: size={}", size);

        Ok(())
    }

    async fn write_metadata(&self, write_metadata: &WriteMetadata) -> Result<(), Error> {
        let mut socket = self.make_socket()?;

        let request = encode(Request::WriteMetadata {
            key: write_metadata.key.clone(),
            metadata: write_metadata.metadata.clone(),
            expire_at: write_metadata.expire_at.clone(),
        });
        socket.send(request, 0).await?;

        let response = decode(socket.recv_msg(0).await?)?;
        eprintln!("write_metadata: {:?}", response);

        Ok(())
    }

    async fn remove(&self, remove: &Remove) -> Result<(), Error> {
        let mut socket = self.make_socket()?;

        let request = encode(Request::Remove {
            key: remove.key.clone(),
        });
        socket.send(request, 0).await?;

        let response = decode(socket.recv_msg(0).await?)?;
        eprintln!("remove: {:?}", response);

        Ok(())
    }

    async fn pull(&self, pull: &Pull) -> Result<(), Error> {
        let mut socket = self.make_socket()?;

        let request = encode(Request::Pull {
            key: pull.key.clone(),
        });
        socket.send(request, 0).await?;

        let response = decode(socket.recv_msg(0).await?)?;
        eprintln!("pull: {:?}", response);

        let (metadata, blob) = match response {
            Some(Response::Pull { metadata, blob }) => (metadata, blob),
            Some(_) => return Err(Error::other("wrong response")),
            None => return Ok(()),
        };

        if self.delay > 0 {
            time::sleep(Duration::from_secs(self.delay)).await;
        }

        let mut file = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&pull.file)?;

        let mut blob_socket = TcpStream::connect(blob.endpoint).await?;
        blob_socket.write_u64(blob.token).await?;
        let size = blob_socket.splice(&mut file, metadata.size).await?;
        eprintln!("pull: size={}", size);

        Ok(())
    }

    async fn push(&self, push: &Push) -> Result<(), Error> {
        let mut file = OpenOptions::new().read(true).open(&push.file)?;
        let size = usize::try_from(file.metadata()?.len()).unwrap();

        let mut socket = self.make_socket()?;

        let request = encode(Request::Push {
            key: push.key.clone(),
            metadata: push.metadata.clone(),
            size,
            expire_at: push.expire_at,
        });
        socket.send(request, 0).await?;

        let response = decode(socket.recv_msg(0).await?)?;
        eprintln!("push: {:?}", response);

        let blob = match response {
            Some(Response::Push { blob }) => blob,
            Some(_) => return Err(Error::other("wrong response")),
            None => return Ok(()),
        };

        if self.delay > 0 {
            time::sleep(Duration::from_secs(self.delay)).await;
        }

        let mut blob_socket = TcpStream::connect(blob.endpoint).await?;
        blob_socket.write_u64(blob.token).await?;
        let size = file.splice(&mut blob_socket, size).await?;
        eprintln!("push: size={}", size);

        Ok(())
    }

    async fn dummy(&self) -> Result<(), Error> {
        let mut socket = Socket::try_from(Context::new().socket(REP)?)?;
        socket.bind(&self.endpoint)?;
        loop {
            let request = socket.recv_msg(0).await?;
            let request = RequestOwner::try_from(request).map_err(Error::other)?;
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

fn encode(request: Request) -> Message {
    Vec::<u8>::from(request).into()
}

fn decode(response: Message) -> Result<Option<Response>, Error> {
    let response = ResponseOwner::try_from(response)
        .map_err(Error::other)?
        .map(ResponseResult::try_from);
    // It is safe to `transpose` because `E` is `capnp::Error`.
    let response = unsafe { response.transpose() }
        .map_err(Error::other)?
        .unzip()
        .map_err(|error| Error::other(format!("{:?}", error.as_ref())))?;
    (*response)
        .map(Response::try_from)
        .transpose()
        .map_err(Error::other)
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let program = Program::parse();
    program.tracing.init();
    program.parameters.init();
    program.execute().await
}
