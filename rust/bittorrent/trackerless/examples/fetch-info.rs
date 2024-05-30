use std::collections::BTreeSet;
use std::fs::File;
use std::io::{Error, Write};
use std::net::SocketAddr;
use std::path::PathBuf;
use std::str::FromStr;
use std::sync::Arc;
use std::time::Duration;

use clap::Parser;
use tokio::{
    net::{TcpListener, TcpSocket, UdpSocket},
    time,
};

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_futures::sink;
use g1_tokio::net::udp::{self as g1_udp, OwnedUdpSink, OwnedUdpStream};

use bittorrent_base::{Features, InfoHash};
use bittorrent_dht::{Dht, DhtGuard};
use bittorrent_extension::Enabled;
use bittorrent_manager::{Manager, ManagerGuard};
use bittorrent_peer::Recvs;
use bittorrent_trackerless::{InfoOwner, Trackerless};
use bittorrent_utp::UtpSocket;

type Fork = bittorrent_udp::Fork<OwnedUdpStream>;
type Fanin = sink::Fanin<OwnedUdpSink>;

/// Fetches the info blob through the metadata protocol extension.
#[derive(Debug, Parser)]
#[command(after_help = ParametersConfig::render())]
struct Program {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    #[arg(long, default_value = "0.0.0.0:6881")]
    self_endpoint: SocketAddr,

    #[arg(long, default_value = "120")]
    timeout: u64,

    #[arg(value_parser = InfoHash::from_str)]
    info_hash: InfoHash,
    info_path: PathBuf,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        let self_features = Features::load();
        assert!(self_features.dht);
        assert!(self_features.extension);
        let self_extensions = Enabled::load();
        assert!(self_extensions.metadata);

        let udp_socket = Arc::new(UdpSocket::bind(self.self_endpoint).await?);
        // Ignore `udp_error_stream` for now.
        let ((dht_stream, dht_sink), (utp_stream, utp_sink), _) =
            self.new_stream_and_sink(udp_socket.clone())?;

        let (peer_endpoints, mut dht_guard) = self
            .lookup_peers(udp_socket.clone(), dht_stream, dht_sink)
            .await?;
        if peer_endpoints.is_empty() {
            return Err(Error::other("no peers available"));
        }

        let mut utp_socket = UtpSocket::new(udp_socket, utp_stream, utp_sink);

        let (manager, mut recvs, mut manager_guard) = self.new_manager(&utp_socket)?;
        for peer_endpoint in peer_endpoints {
            manager.connect(peer_endpoint, None);
        }

        let trackerless = Trackerless::new(self.info_hash.clone(), &manager, &mut recvs);
        let info = time::timeout(Duration::from_secs(self.timeout), trackerless.fetch())
            .await
            .map_err(|_| Error::other("timeout on fetch info blob"))?
            .map_err(Error::other)?;
        File::create(&self.info_path)?.write_all(InfoOwner::as_slice(&info))?;

        tokio::join!(
            async {
                match dht_guard.shutdown().await {
                    Ok(Ok(())) => {}
                    Ok(Err(error)) => tracing::warn!(%error, "dht error"),
                    Err(error) => tracing::warn!(%error, "dht shutdown error"),
                }
            },
            async {
                if let Err(error) = utp_socket.shutdown().await {
                    tracing::warn!(%error, "utp socket error");
                }
            },
            async {
                match manager_guard.shutdown().await {
                    Ok(Ok(())) => {}
                    Ok(Err(error)) => tracing::warn!(%error, "peer manager error"),
                    Err(error) => tracing::warn!(%error, "peer manager shutdown error"),
                }
            },
        );

        Ok(())
    }

    fn new_stream_and_sink(
        &self,
        udp_socket: Arc<UdpSocket>,
    ) -> Result<((Fork, Fanin), (Fork, Fanin), Fork), Error> {
        let (stream, sink) = g1_udp::UdpSocket::new(udp_socket).into_split();
        let (dht_stream, utp_stream, udp_error_stream) = bittorrent_udp::fork(stream);
        let [dht_sink, utp_sink] = sink::fanin(sink);
        Ok((
            (dht_stream, dht_sink),
            (utp_stream, utp_sink),
            udp_error_stream,
        ))
    }

    fn new_manager(&self, utp_socket: &UtpSocket) -> Result<(Manager, Recvs, ManagerGuard), Error> {
        let (tcp_listener_v4, tcp_listener_v6, utp_socket_v4, utp_socket_v6) =
            if self.self_endpoint.is_ipv4() {
                (
                    Some(self.new_tcp_listener(TcpSocket::new_v4()?)?),
                    None,
                    Some(utp_socket),
                    None,
                )
            } else {
                assert!(self.self_endpoint.is_ipv6());
                (
                    None,
                    Some(self.new_tcp_listener(TcpSocket::new_v6()?)?),
                    None,
                    Some(utp_socket),
                )
            };
        Ok(Manager::spawn(
            self.info_hash.clone(),
            tcp_listener_v4,
            tcp_listener_v6,
            utp_socket_v4,
            utp_socket_v6,
        ))
    }

    fn new_tcp_listener(&self, socket: TcpSocket) -> Result<TcpListener, Error> {
        socket.set_reuseaddr(true)?;
        socket.bind(self.self_endpoint)?;
        socket.listen(256)
    }

    async fn lookup_peers(
        &self,
        udp_socket: Arc<UdpSocket>,
        dht_stream: Fork,
        dht_sink: Fanin,
    ) -> Result<(BTreeSet<SocketAddr>, DhtGuard), Error> {
        let (dht, guard) = Dht::spawn(udp_socket.local_addr()?, dht_stream, dht_sink);
        let (peers, _) = dht.lookup_peers(self.info_hash.clone()).await;
        Ok((peers, guard))
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let program = Program::parse();
    program.tracing.init();
    program.parameters.init();
    program.execute().await
}
