use std::io::{Error, ErrorKind};
use std::marker::Unpin;
use std::net::SocketAddr;
use std::sync::Arc;

use bytes::{Buf, Bytes};
use clap::{Parser, ValueEnum};
use futures::{sink::SinkExt, stream::StreamExt};
use tokio::{
    io::{self, AsyncReadExt, AsyncWriteExt},
    net::{self, TcpListener, TcpSocket},
};

use g1_base::str::Hex;
use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_tokio::{
    bstream::{StreamIntoSplit, StreamRecv, StreamSend},
    io::{DynStream, DynStreamRecv, DynStreamSend},
    net::tcp::TcpStream,
    net::udp::UdpSocket,
};

use bittorrent_base::{Features, InfoHash};
use bittorrent_mse::MseStream;
use bittorrent_peer::Peer;
use bittorrent_socket::{Message, Socket};
use bittorrent_utp::UtpSocket;

#[derive(Debug, Parser)]
#[command(after_help = ParametersConfig::render())]
struct NetCat {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    #[arg(long, value_enum, default_value_t = Protocol::Tcp)]
    protocol: Protocol,

    #[arg(long, value_name = "INFO_HASH")]
    mse: Option<String>,

    #[arg(long)]
    info_hash: Option<String>,

    #[arg(long, short)]
    listen: bool,
    #[arg(default_value = "127.0.0.1:8000")]
    endpoint: SocketAddr,

    #[arg(long, conflicts_with("no_recv"))]
    recv: bool,
    #[arg(long)]
    no_recv: bool,

    #[arg(long, conflicts_with("no_send"))]
    send: bool,
    #[arg(long)]
    no_send: bool,
}

#[derive(Clone, Debug, Eq, PartialEq, ValueEnum)]
enum Protocol {
    Bt,
    BtPeer,
    Tcp,
    Udp,
    Utp,
}

impl NetCat {
    async fn execute(&self) -> Result<(), Error> {
        match self.protocol {
            Protocol::Bt => return self.execute_bt().await,
            Protocol::BtPeer => return self.execute_bt_peer().await,
            Protocol::Tcp => return self.execute_tcp().await,
            Protocol::Udp => return self.execute_udp().await,
            Protocol::Utp => return self.execute_utp().await,
        }
    }

    /// Receives/sends one piece from/to a peer.
    async fn execute_bt(&self) -> Result<(), Error> {
        if self.recv || self.no_recv {
            return Err(Error::other(
                "bt mode does not support `--recv` nor `--no-recv`",
            ));
        }
        if self.send || self.no_send {
            return Err(Error::other(
                "bt mode does not support `--send` nor `--no-send`",
            ));
        }

        let (mut socket, _) = self.make_bittorrent_socket().await?;

        if self.listen {
            let message = socket.recv().await?;
            let Message::Piece(_, mut payload) = message else {
                return Err(Error::other(format!("expect piece: {:?}", message)));
            };
            io::stdout().write_all_buf(&mut payload).await?;
        } else {
            let mut payload = Vec::new();
            io::stdin().read_to_end(&mut payload).await?;
            socket
                .send(Message::Piece(
                    (0, 0, payload.len().try_into().unwrap()).into(),
                    payload.into(),
                ))
                .await?;
        }

        socket.shutdown().await
    }

    /// Receives/sends one piece from/to a peer.
    async fn execute_bt_peer(&self) -> Result<(), Error> {
        if self.recv || self.no_recv {
            return Err(Error::other(
                "bt-peer mode does not support `--recv` nor `--no-recv`",
            ));
        }
        if self.send || self.no_send {
            return Err(Error::other(
                "bt-peer mode does not support `--send` nor `--no-send`",
            ));
        }

        let (socket, peer_endpoint) = self.make_bittorrent_socket().await?;
        let (mut recvs, sends) = bittorrent_peer::new_channels();
        let (peer, mut guard) = Peer::spawn(socket, peer_endpoint, sends);

        if self.listen {
            let response_recv = peer.request((0, 0, 4).into()).unwrap().unwrap();
            let size = u64::from(response_recv.await.map_err(Error::other)?.get_u32());
            let response_recv = peer.request((0, 1, size).into()).unwrap().unwrap();
            let mut payload = response_recv.await.map_err(Error::other)?;
            io::stdout().write_all_buf(&mut payload).await?;
            guard.shutdown().await?
        } else {
            let mut payload = Vec::new();
            io::stdin().read_to_end(&mut payload).await?;
            let size = Bytes::copy_from_slice(&u32::try_from(payload.len()).unwrap().to_be_bytes());

            peer.set_self_choking(false);
            let (_, _, response_send) = recvs.request_recv.recv().await.unwrap();
            response_send.send(size).unwrap();
            let (_, _, response_send) = recvs.request_recv.recv().await.unwrap();
            response_send.send(payload.into()).unwrap();

            guard.join().await;
            let result = guard.shutdown().await?;
            if result
                .as_ref()
                .is_err_and(|error| error.kind() == ErrorKind::UnexpectedEof)
            {
                Ok(())
            } else {
                result
            }
        }
    }

    async fn execute_tcp(&self) -> Result<(), Error> {
        let stream = if self.listen {
            let (stream, _) = self.bind()?.accept().await?;
            TcpStream::from(stream)
        } else {
            self.connect().await?
        };
        let stream = self.mse_handshake(stream).await?;
        self.copy_bidirectional(stream).await
    }

    /// Receives/sends one datagram from/to a peer.
    async fn execute_udp(&self) -> Result<(), Error> {
        if self.mse.is_some() {
            return Err(Error::other("udp mode does not support `--mse`"));
        }
        if self.recv || self.no_recv {
            return Err(Error::other(
                "udp mode does not support `--recv` nor `--no-recv`",
            ));
        }
        if self.send || self.no_send {
            return Err(Error::other(
                "udp mode does not support `--send` nor `--no-send`",
            ));
        }
        if self.listen {
            let mut socket = UdpSocket::new(net::UdpSocket::bind(self.endpoint).await?);
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
            socket.feed((self.endpoint, payload.into())).await?;
            socket.close().await
        }
    }

    async fn execute_utp(&self) -> Result<(), Error> {
        let (mut socket, stream) = if self.listen {
            let socket = self.new_utp_socket(net::UdpSocket::bind(self.endpoint).await?);
            let stream = socket.listener().accept().await?;
            eprintln!("peer endpoint: {}", stream.peer_endpoint());
            (socket, stream)
        } else {
            let socket = self.new_utp_socket(net::UdpSocket::bind("127.0.0.1:0").await?);
            eprintln!("local endpoint: {}", socket.socket().local_addr()?);
            let stream = socket.connector().connect(self.endpoint).await?;
            (socket, stream)
        };
        let stream = self.mse_handshake(stream).await?;
        self.copy_bidirectional(stream).await?;
        socket.shutdown().await
    }

    fn bind(&self) -> Result<TcpListener, Error> {
        let socket = self.make_socket()?;
        socket.bind(self.endpoint)?;
        Ok(socket.listen(8)?)
    }

    async fn connect(&self) -> Result<TcpStream, Error> {
        Ok(self.make_socket()?.connect(self.endpoint).await?.into())
    }

    fn make_socket(&self) -> Result<TcpSocket, Error> {
        let socket = TcpSocket::new_v4()?;
        socket.set_reuseaddr(true)?;
        Ok(socket)
    }

    fn new_utp_socket(&self, socket: net::UdpSocket) -> UtpSocket {
        let socket = Arc::new(socket);
        let (stream, sink) = UdpSocket::new(socket.clone()).into_split();
        UtpSocket::new(socket, stream, sink)
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
            None => MseStream::new_plaintext(stream),
        })
    }

    async fn make_bittorrent_socket(
        &self,
    ) -> Result<(Socket<DynStream<'static>>, SocketAddr), Error> {
        let info_hash = self
            .parse_info_hash()?
            .ok_or_else(|| Error::other("`--info-hash` is required"))?;

        let stream = if self.listen {
            let (stream, _) = self.bind()?.accept().await?;
            TcpStream::from(stream)
        } else {
            self.connect().await?
        };
        let peer_endpoint = stream.stream().peer_addr()?;
        let stream = self.mse_handshake(stream).await?.into();

        let self_id = bittorrent_base::self_id().clone();
        let self_features = Features::load();
        eprintln!("self id: {:?}", self_id);
        eprintln!("self features: {:?}", self_features);
        let socket = if self.listen {
            Socket::accept(stream, info_hash, self_id, self_features, None).await
        } else {
            Socket::connect(stream, info_hash, self_id, self_features, None).await
        }?;
        eprintln!("peer id: {:?}", socket.peer_id());
        eprintln!("peer features: {:?}", socket.peer_features());

        Ok((socket, peer_endpoint))
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

    fn parse_info_hash(&self) -> Result<Option<InfoHash>, Error> {
        self.info_hash
            .as_ref()
            .map(|info_hash| match info_hash.as_str().try_into() {
                Ok(Hex(hex)) => Ok(InfoHash::new(hex)),
                Err(error) => Err(Error::other(error)),
            })
            .transpose()
    }

    async fn copy_bidirectional<Stream, Source, Sink>(
        &self,
        stream: MseStream<Stream>,
    ) -> Result<(), Error>
    where
        Stream: StreamIntoSplit<OwnedRecvHalf = Source, OwnedSendHalf = Sink>,
        Source: StreamRecv<Error = Error> + Send,
        Sink: StreamSend<Error = Error> + Send,
    {
        let (source, sink): (DynStreamRecv, DynStreamSend) = match stream {
            MseStream::Rc4(stream) => {
                let (source, sink) = stream.into_split();
                (Box::new(source), Box::new(sink))
            }
            MseStream::Plaintext(stream) => {
                let (source, sink) = stream.into_split();
                (Box::new(source), Box::new(sink))
            }
        };
        tokio::try_join!(
            async {
                if self.should_recv() {
                    recv(source, io::stdout()).await
                } else {
                    drop(source);
                    Ok(())
                }
            },
            async {
                if self.should_send() {
                    send(io::stdin(), sink).await
                } else {
                    drop(sink);
                    Ok(())
                }
            },
        )?;
        Ok(())
    }

    fn should_recv(&self) -> bool {
        assert_eq!(self.recv && self.no_recv, false);
        if self.recv {
            true
        } else if self.no_recv {
            false
        } else {
            self.listen
        }
    }

    fn should_send(&self) -> bool {
        assert_eq!(self.send && self.no_send, false);
        if self.send {
            true
        } else if self.no_send {
            false
        } else {
            !self.listen
        }
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
