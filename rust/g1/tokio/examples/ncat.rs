#![feature(io_error_other)]

use std::io::Error;
use std::marker::Unpin;
use std::net::{Ipv4Addr, SocketAddr};

use clap::Parser;
use tokio::{
    io::{self, AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpSocket},
};

use g1_tokio::{
    bstream::{StreamRecv, StreamSend},
    net::tcp::TcpStream,
};

#[derive(Debug, Parser)]
struct NetCat {
    #[arg(long, short)]
    listen: bool,
    #[arg(default_value = "127.0.0.1")]
    address: String,
    #[arg(default_value = "8000")]
    port: u16,
}

impl NetCat {
    async fn execute(&self) -> Result<(), Error> {
        if self.listen {
            let (stream, _) = self.bind()?.accept().await?;
            recv(TcpStream::from(stream), io::stdout()).await
        } else {
            send(io::stdin(), self.connect().await?).await
        }
    }

    fn bind(&self) -> Result<TcpListener, Error> {
        let socket = self.make_socket()?;
        socket.bind(self.parse_endpoint()?)?;
        Ok(socket.listen(8)?)
    }

    async fn connect(&self) -> Result<TcpStream, Error> {
        Ok(self
            .make_socket()?
            .connect(self.parse_endpoint()?)
            .await?
            .into())
    }

    fn parse_endpoint(&self) -> Result<SocketAddr, Error> {
        let address: Ipv4Addr = self.address.parse().map_err(Error::other)?;
        Ok(SocketAddr::from((address, self.port)))
    }

    fn make_socket(&self) -> Result<TcpSocket, Error> {
        let socket = TcpSocket::new_v4()?;
        socket.set_reuseaddr(true)?;
        Ok(socket)
    }
}

async fn recv<Source, Sink>(mut source: Source, mut sink: Sink) -> Result<(), Error>
where
    Source: StreamRecv<Error = Error>,
    Sink: AsyncWriteExt + Unpin,
{
    while source.recv_or_eof().await?.is_some() {
        sink.write_all_buf(&mut *source.buffer()).await?;
    }
    Ok(())
}

async fn send<Source, Sink>(mut source: Source, mut sink: Sink) -> Result<(), Error>
where
    Source: AsyncReadExt + Unpin,
    Sink: StreamSend<Error = Error>,
{
    while source.read_buf(&mut *sink.buffer()).await? > 0 {
        sink.send_all().await?;
    }
    sink.shutdown().await?;
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    NetCat::parse().execute().await
}
