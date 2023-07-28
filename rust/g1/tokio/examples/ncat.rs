#![feature(io_error_other)]

use std::io::{Error, ErrorKind};
use std::marker::Unpin;
use std::net::{Ipv4Addr, SocketAddr};

use clap::{Parser, ValueEnum};
use futures::{sink::SinkExt, stream::StreamExt};
use tokio::{
    io::{self, AsyncReadExt, AsyncWriteExt},
    net::{self, TcpListener, TcpSocket},
};

use g1_base::str::Hex;
use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_tokio::{
    bstream::{StreamRecv, StreamSend},
    net::tcp::TcpStream,
    net::udp::UdpSocket,
};

use bittorrent_mse::MseStream;

#[derive(Debug, Parser)]
struct NetCat {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    #[arg(long, value_enum, default_value_t = Protocol::Tcp)]
    protocol: Protocol,

    #[arg(long, value_name = "INFO_HASH")]
    mse: Option<String>,

    #[arg(long, short)]
    listen: bool,
    #[arg(default_value = "127.0.0.1")]
    address: String,
    #[arg(default_value = "8000")]
    port: u16,
}

#[derive(Clone, Debug, Eq, PartialEq, ValueEnum)]
enum Protocol {
    Tcp,
    Udp,
}

impl NetCat {
    async fn execute(&self) -> Result<(), Error> {
        if self.protocol == Protocol::Udp {
            return self.execute_udp().await;
        }

        let stream = if self.listen {
            let (stream, _) = self.bind()?.accept().await?;
            TcpStream::from(stream)
        } else {
            self.connect().await?
        };
        let stream = self.mse_handshake(stream).await?;
        if self.listen {
            recv(stream, io::stdout()).await
        } else {
            send(io::stdin(), stream).await
        }
    }

    /// Receives/sends one datagram from/to a peer.
    async fn execute_udp(&self) -> Result<(), Error> {
        if self.mse.is_some() {
            return Err(Error::other("udp mode does not support `--mse`"));
        }
        if self.listen {
            let mut socket = UdpSocket::new(net::UdpSocket::bind(self.parse_endpoint()?).await?);
            let (peer, mut payload) = socket
                .next()
                .await
                .ok_or_else(|| Error::from(ErrorKind::UnexpectedEof))??;
            eprintln!("receive datagram from: {}", peer);
            io::stdout().write_all_buf(&mut payload).await
        } else {
            let mut socket = UdpSocket::new(net::UdpSocket::bind("127.0.0.1:0").await?);
            eprintln!("local address: {}", socket.socket().local_addr()?);
            let mut payload = Vec::new();
            io::stdin().read_to_end(&mut payload).await?;
            socket
                .feed((self.parse_endpoint()?, payload.into()))
                .await?;
            socket.close().await
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

    async fn mse_handshake<Stream>(&self, stream: Stream) -> Result<MseStream<Stream>, Error>
    where
        Stream: StreamRecv<Error = Error> + StreamSend<Error = Error> + Send,
    {
        Ok(match self.parse_mse()? {
            Some(info_hash) => {
                if self.listen {
                    bittorrent_mse::accept(stream, &info_hash).await?
                } else {
                    bittorrent_mse::connect(stream, &info_hash).await?
                }
            }
            None => bittorrent_mse::wrap(stream),
        })
    }

    fn parse_mse(&self) -> Result<Option<Vec<u8>>, Error> {
        self.mse
            .as_ref()
            .map(|info_hash| match info_hash.parse::<Hex<Vec<u8>>>() {
                Ok(Hex(hex)) => Ok(hex),
                Err(error) => Err(Error::other(error)),
            })
            .transpose()
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
    let ncat = NetCat::parse();
    ncat.tracing.init();
    ncat.parameters.init();
    ncat.execute().await
}
