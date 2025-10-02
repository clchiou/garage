use std::io::Error;

use tokio::net::TcpSocket;

use bt_base::PeerEndpoint;

use crate::base::RawConn;

pub(super) async fn connect(
    self_endpoint: PeerEndpoint,
    peer_endpoint: PeerEndpoint,
) -> Result<(PeerEndpoint, RawConn), Error> {
    let socket = if self_endpoint.is_ipv4() {
        TcpSocket::new_v4()
    } else {
        assert!(self_endpoint.is_ipv6());
        TcpSocket::new_v6()
    }?;
    socket.set_reuseport(true)?;
    socket.bind(self_endpoint)?;
    let stream = socket.connect(peer_endpoint).await?;
    Ok((stream.local_addr()?, RawConn::Tcp(stream)))
}
