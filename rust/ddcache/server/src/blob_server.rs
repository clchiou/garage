use std::io::{Error, ErrorKind};
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use tokio::io::AsyncReadExt;
use tokio::net::{TcpListener, TcpSocket, TcpStream};
use tokio::sync::mpsc::{self, Receiver, Sender};
use tokio::time::{self, Instant};
use tracing::Instrument;

use g1_tokio::os::{SendFile, Splice};
use g1_tokio::task::{Cancel, JoinQueue};

use ddcache_proto::BlobEndpoint;

use crate::state::{Io, State};
use crate::Guard;

#[derive(Debug)]
pub(crate) struct Actor {
    cancel: Cancel,
    accept_recv: Receiver<(TcpStream, SocketAddr)>,
    state: Arc<State>,
    timeout: Duration,
    tasks: JoinQueue<Result<(), Error>>,
}

#[derive(Debug)]
struct Acceptor {
    cancel: Cancel,
    listener: TcpListener,
    accept_send: Sender<(TcpStream, SocketAddr)>,
}

impl Actor {
    pub(crate) fn spawn(state: Arc<State>) -> Result<(Vec<BlobEndpoint>, Guard), Error> {
        let mut endpoints = Vec::with_capacity(crate::blob_endpoints().len());
        let (accept_send, accept_recv) =
            mpsc::channel((*crate::tcp_listen_backlog()).try_into().unwrap());
        let tasks = JoinQueue::new();
        for endpoint in crate::blob_endpoints() {
            let (listener, endpoint) = new_listener(*endpoint)?;
            endpoints.push(endpoint);
            tasks
                .push(Guard::spawn(|cancel| {
                    Acceptor::new(cancel, listener, accept_send.clone())
                        .run()
                        .instrument(tracing::info_span!("ddcache/blob-accept", %endpoint))
                }))
                .unwrap();
        }
        tracing::info!(?endpoints, "blob bind");
        Ok((
            endpoints,
            Guard::spawn(move |cancel| Self::new(cancel, accept_recv, state, tasks).run()),
        ))
    }

    fn new(
        cancel: Cancel,
        accept_recv: Receiver<(TcpStream, SocketAddr)>,
        state: Arc<State>,
        tasks: JoinQueue<Result<(), Error>>,
    ) -> Self {
        Self {
            cancel,
            accept_recv,
            state,
            timeout: *crate::blob_request_timeout(),
            tasks,
        }
    }

    async fn run(mut self) -> Result<(), Error> {
        loop {
            tokio::select! {
                () = self.cancel.wait() => break,

                accept = self.accept_recv.recv() => {
                    self.handle_accept(accept.unwrap());
                }

                guard = self.tasks.join_next() => {
                    let Some(guard) = guard else { break };
                    self.handle_task(guard)?;
                }
            }
        }

        self.tasks.cancel();
        while let Some(guard) = self.tasks.join_next().await {
            self.handle_task(guard)?;
        }

        Ok(())
    }

    fn handle_accept(&self, (stream, client_endpoint): (TcpStream, SocketAddr)) {
        let state = self.state.clone();
        let timeout = self.timeout;
        self.tasks
            .push(Guard::spawn(move |cancel| {
                async move {
                    tokio::select! {
                        () = cancel.wait() => Ok(()),
                        result = txrx_blob(stream, state, timeout) => result,
                    }
                }
                .instrument(tracing::info_span!("ddcache/blob", %client_endpoint))
            }))
            .unwrap();
    }

    fn handle_task(&self, mut guard: Guard) -> Result<(), Error> {
        match guard.take_result() {
            Ok(result) => result,
            Err(error) => {
                tracing::warn!(%error, "blob handler task error");
                Ok(())
            }
        }
    }
}

fn new_listener(endpoint: BlobEndpoint) -> Result<(TcpListener, BlobEndpoint), Error> {
    let socket = if endpoint.is_ipv4() {
        TcpSocket::new_v4()
    } else {
        assert!(endpoint.is_ipv6());
        TcpSocket::new_v6()
    }?;
    socket.set_reuseport(true)?;
    socket.bind(endpoint)?;
    let listener = socket.listen(*crate::tcp_listen_backlog())?;
    let endpoint = listener.local_addr()?;
    Ok((listener, endpoint))
}

impl Acceptor {
    fn new(
        cancel: Cancel,
        listener: TcpListener,
        accept_send: Sender<(TcpStream, SocketAddr)>,
    ) -> Self {
        Self {
            cancel,
            listener,
            accept_send,
        }
    }

    async fn run(self) -> Result<(), Error> {
        loop {
            tokio::select! {
                () = self.cancel.wait() => break,

                accept = self.listener.accept() => {
                    let accept = accept?;
                    tracing::debug!(client_endpoint = %accept.1, "accept");
                    if self.accept_send.send(accept).await.is_err() {
                        break;
                    }
                }
            }
        }
        Ok(())
    }
}

async fn txrx_blob(
    mut stream: TcpStream,
    state: Arc<State>,
    timeout: Duration,
) -> Result<(), Error> {
    // TODO: How can we ensure that `read_u64` does not buffer data internally?
    let token = stream.read_u64().await?;
    let Some(io) = state.remove(token) else {
        tracing::debug!(token, "token not found");
        return Ok(());
    };

    // Unregister `stream` from the tokio reactor; otherwise, `sendfile` will return `EEXIST` when
    // it attempts to register `stream` with the reactor via `AsyncFd`.
    let mut stream = stream.into_std()?;

    match io {
        Io::Reader((mut reader, _permit)) => {
            let expect = usize::try_from(reader.size()).unwrap();

            let start = Instant::now();
            let size = time::timeout(timeout, stream.sendfile(reader.file(), None, expect))
                .await
                .map_err(|_| Error::new(ErrorKind::TimedOut, "send blob timeout"))??;
            let duration = start.elapsed();

            if size != expect {
                return Err(Error::new(
                    ErrorKind::UnexpectedEof,
                    format!("send blob: expect {} bytes: {}", expect, size),
                ));
            }

            tracing::debug!(token, size, ?duration, "send blob");
        }
        Io::Writer((mut writer, expect, _permit)) => {
            writer.open()?;

            let start = Instant::now();
            let size = time::timeout(timeout, stream.splice(writer.file(), expect))
                .await
                .map_err(|_| Error::new(ErrorKind::TimedOut, "recv blob timeout"))??;
            let duration = start.elapsed();

            if size != expect {
                return Err(Error::new(
                    ErrorKind::UnexpectedEof,
                    format!("recv blob: expect {} bytes: {}", expect, size),
                ));
            }
            writer.commit()?;

            tracing::debug!(token, size, ?duration, "recv blob");
        }
    }
    Ok(())
}
