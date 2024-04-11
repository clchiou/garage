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

use g1_capnp::owner::Owner;
use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_tokio::os::Splice;
use g1_zmq::Socket;

use ddcache_proto::ddcache_capnp::{endpoint, request, response};
use ddcache_proto::{
    BlobEndpoint, Endpoint, RequestOwner, ResponseBuilder, ResponseOwner, ResponseResult, Token,
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
    Ping,
    Read(Read),
    ReadMetadata(ReadMetadata),
    Write(Write),
    Cancel(Cancel),
    Dummy,
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
    file: PathBuf,
}

#[derive(Args, Debug)]
struct Cancel {
    token: Token,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        match &self.command {
            Command::Ping => self.ping().await?,
            Command::Read(read) => self.read(read).await?,
            Command::ReadMetadata(read_metadata) => self.read_metadata(read_metadata).await?,
            Command::Write(write) => self.write(write).await?,
            Command::Cancel(cancel) => self.cancel(cancel).await?,
            Command::Dummy => self.dummy().await?,
        }
        Ok(())
    }

    async fn ping(&self) -> Result<(), Error> {
        let socket = self.make_socket()?;

        let request = make_request(|mut request| request.set_ping(()));
        socket.send(request, 0).await?;

        let response = socket.recv_msg(0).await?;
        let response = ResponseOwner::try_from(response).map_err(Error::other)?;
        eprintln!("ping: {:?}", &*response);

        Ok(())
    }

    async fn read(&self, read: &Read) -> Result<(), Error> {
        let socket = self.make_socket()?;

        let request = make_request(|request| request.init_read().set_key(&read.key));
        socket.send(request, 0).await?;

        let response = decode(socket.recv_msg(0).await?)?;
        eprintln!("read: {:?}", &*response);
        let Some(response) = response.transpose() else {
            return Ok(());
        };
        let Ok(response::Read(Ok(response))) = response.which() else {
            return Err(Error::other("wrong response"));
        };

        let metadata = response.get_metadata().map_err(Error::other)?;
        eprintln!("read: metadata=\"{}\"", metadata.escape_ascii());

        let size = response.get_size();

        let endpoint = decode_endpoint(response.get_endpoint())?;
        let token = response.get_token();

        if self.delay > 0 {
            time::sleep(Duration::from_secs(self.delay)).await;
        }

        let mut file = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&read.file)?;

        let mut blob_socket = TcpStream::connect(endpoint).await?;
        blob_socket.write_u64(token).await?;
        let size = blob_socket
            .splice(&mut file, size.try_into().unwrap())
            .await?;
        eprintln!("read: size={}", size);

        Ok(())
    }

    async fn read_metadata(&self, read_metadata: &ReadMetadata) -> Result<(), Error> {
        let socket = self.make_socket()?;

        let request =
            make_request(|request| request.init_read_metadata().set_key(&read_metadata.key));
        socket.send(request, 0).await?;

        let response = decode(socket.recv_msg(0).await?)?;
        eprintln!("read_metadata: {:?}", &*response);

        Ok(())
    }

    async fn write(&self, write: &Write) -> Result<(), Error> {
        let mut file = OpenOptions::new().read(true).open(&write.file)?;
        let size = file.metadata()?.len();

        let socket = self.make_socket()?;

        let request = make_request(|request| {
            let mut request = request.init_write();
            request.set_key(&write.key);
            if let Some(metadata) = &write.metadata {
                request.set_metadata(metadata);
            }
            request.set_size(size.try_into().unwrap());
        });
        socket.send(request, 0).await?;

        let response = decode(socket.recv_msg(0).await?)?;
        eprintln!("write: {:?}", &*response);
        let Some(response) = response.transpose() else {
            return Ok(());
        };
        let Ok(response::Write(Ok(response))) = response.which() else {
            return Err(Error::other("wrong response"));
        };

        let endpoint = decode_endpoint(response.get_endpoint())?;
        let token = response.get_token();

        if self.delay > 0 {
            time::sleep(Duration::from_secs(self.delay)).await;
        }

        let mut blob_socket = TcpStream::connect(endpoint).await?;
        blob_socket.write_u64(token).await?;
        let size = file
            .splice(&mut blob_socket, size.try_into().unwrap())
            .await?;
        eprintln!("write: size={}", size);

        Ok(())
    }

    async fn cancel(&self, cancel: &Cancel) -> Result<(), Error> {
        let socket = self.make_socket()?;

        let request = make_request(|mut request| request.set_cancel(cancel.token));
        socket.send(request, 0).await?;

        let response = decode(socket.recv_msg(0).await?)?;
        eprintln!("cancel: {:?}", &*response);

        Ok(())
    }

    fn make_socket(&self) -> Result<Socket, Error> {
        let socket = Socket::try_from(Context::new().socket(REQ)?)?;
        socket.connect(&self.endpoint)?;
        Ok(socket)
    }

    async fn dummy(&self) -> Result<(), Error> {
        let socket = Socket::try_from(Context::new().socket(REP)?)?;
        socket.bind(&self.endpoint)?;
        loop {
            let request = socket.recv_msg(0).await?;
            let request = RequestOwner::try_from(request).map_err(Error::other)?;
            eprintln!("request: {:?}", &*request);

            let mut response = message::Builder::new_default();
            response
                .init_root::<ResponseBuilder>()
                .init_err()
                .set_none(());
            let response = serialize::write_message_to_words(&response);
            socket.send(response, 0).await?;
        }
    }
}

fn make_request<F>(init: F) -> Message
where
    F: FnOnce(request::Builder),
{
    let mut request = message::Builder::new_default();
    init(request.init_root::<request::Builder>());
    serialize::write_message_to_words(&request).into()
}

fn decode(response: Message) -> Result<Owner<Message, Option<response::Reader<'static>>>, Error> {
    let response = ResponseOwner::try_from(response)
        .map_err(Error::other)?
        .map(ResponseResult::try_from);
    // It is safe to `transpose` because `E` is `capnp::Error`.
    unsafe { response.transpose() }
        .map_err(Error::other)?
        .unzip()
        .map_err(|error| Error::other(format!("{:?}", error.as_ref())))
}

fn decode_endpoint(
    endpoint: Result<endpoint::Reader, capnp::Error>,
) -> Result<BlobEndpoint, Error> {
    let endpoint: Result<_, capnp::Error> = try { BlobEndpoint::try_from(endpoint?)? };
    endpoint.map_err(Error::other)
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let program = Program::parse();
    program.tracing.init();
    program.parameters.init();
    program.execute().await
}
