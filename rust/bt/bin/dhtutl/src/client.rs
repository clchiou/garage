use std::io::Error;
use std::net::{SocketAddr, SocketAddrV4};
use std::time::Duration;

use bytes::{Bytes, BytesMut};
use tokio::net::UdpSocket;
use tokio::time;

use bt_dht_proto::{Message, Payload};

macro_rules! ensure {
    ($predicate:expr, $fmt:literal $(, $arg:expr)* $(,)?) => {
        if !$predicate {
            return Err(Error::other(format!($fmt $(, $arg)*)));
        }
    };
}

macro_rules! ensure_eq {
    ($actual:expr, $expect:expr, $name:literal $(,)?) => {{
        let actual = &$actual;
        let expect = &$expect;
        ensure!(
            actual == expect,
            "expect {} {:?}: {:?}",
            $name,
            expect,
            actual,
        );
    }};
}

#[derive(Debug)]
pub(crate) struct Client {
    socket: UdpSocket,
    recv_timeout: Duration,
}

impl Client {
    pub(crate) fn new(socket: UdpSocket, recv_timeout: Duration) -> Self {
        Self {
            socket,
            recv_timeout,
        }
    }

    pub(crate) async fn request(
        &self,
        node_endpoint: SocketAddrV4,
        query: Message,
    ) -> Result<(Bytes, Message), Error> {
        tracing::debug!(?query);
        let raw_query = bt_bencode::to_bytes(&query).map_err(Error::other)?;

        let num_sent = self.socket.send_to(&raw_query, node_endpoint).await?;
        ensure_eq!(num_sent, raw_query.len(), "sending num bytes");

        // We need to allocate a large buffer because `UdpSocket` discards excess data.
        let mut raw_response = BytesMut::with_capacity(65536);
        let (_, recv_endpoint) = time::timeout(
            self.recv_timeout,
            self.socket.recv_buf_from(&mut raw_response),
        )
        .await
        .map_err(Error::other)??;

        let raw_response = raw_response.freeze();
        tracing::debug!(?raw_response, "recv");

        ensure_eq!(recv_endpoint, SocketAddr::V4(node_endpoint), "recv from");

        let mut buf = &*raw_response;
        let response = bt_bencode::from_buf::<_, Message>(&mut buf).map_err(Error::other)?;
        tracing::debug!(?response);

        if !buf.is_empty() {
            tracing::warn!(trailing_data = %buf.escape_ascii());
        }

        ensure_eq!(response.txid, query.txid, "transaction id");

        ensure!(
            matches!(response.payload, Payload::Response(_) | Payload::Error(_)),
            "expect response or error: {response:?}",
        );

        Ok((raw_response, response))
    }
}
