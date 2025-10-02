use std::io::Error;
use std::sync::Arc;

use tokio::net::{TcpListener, TcpSocket};

use g1_tokio::task::Cancel;

use bt_base::PeerEndpoint;

use crate::NetGuard;
use crate::base::{RawConn, Shared};

struct ListenActor {
    shared: Arc<Shared>,
    listener: TcpListener,
}

// TODO: Make these configurable.
const TCP_BACKLOG: u32 = 256;

pub(crate) fn spawn(shared: Arc<Shared>, self_endpoint: PeerEndpoint) -> Result<NetGuard, Error> {
    let actor = ListenActor {
        shared,
        listener: make_listener(self_endpoint)?,
    };
    Ok(NetGuard::spawn(move |cancel| actor.run(cancel)))
}

fn make_listener(self_endpoint: PeerEndpoint) -> Result<TcpListener, Error> {
    let socket = if self_endpoint.is_ipv4() {
        TcpSocket::new_v4()
    } else {
        assert!(self_endpoint.is_ipv6());
        TcpSocket::new_v6()
    }?;
    socket.set_reuseport(true)?;
    socket.bind(self_endpoint)?;
    socket.listen(TCP_BACKLOG)
}

impl ListenActor {
    async fn run(self, cancel: Cancel) -> Result<(), Error> {
        tokio::select! {
            () = cancel.wait() => Ok(()),
            result = self.listen() => result,
        }
    }

    async fn listen(&self) -> Result<(), Error> {
        let self_endpoint = self.listener.local_addr()?;
        tracing::info!(%self_endpoint, "bind");

        loop {
            let (raw_conn, peer_endpoint) = self.listener.accept().await?;
            tracing::debug!(%self_endpoint, %peer_endpoint, "accept");

            let guard = super::spawn(
                self.shared.clone(),
                self_endpoint,
                peer_endpoint,
                RawConn::Tcp(raw_conn),
            );

            if let Err(mut guard) = self.shared.handshake_tasks.push(guard) {
                match guard.shutdown().await {
                    Ok(()) => {}
                    Err(error) => tracing::warn!(%self_endpoint, %error, "accept shutdown"),
                }
                break;
            }
        }
        Ok(())
    }
}
