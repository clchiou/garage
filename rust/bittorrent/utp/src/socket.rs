use std::collections::HashMap;
use std::io::{Error, ErrorKind};
use std::net::SocketAddr;
use std::panic;
use std::sync::Arc;

use bytes::{Bytes, BytesMut};
use futures::{
    sink::{Sink, SinkExt},
    stream::{Stream, TryStreamExt},
};
use tokio::{
    net::UdpSocket,
    sync::{mpsc, oneshot},
    task::Id,
};

use g1_tokio::{
    sync::mpmc,
    task::{Cancel, JoinGuard, JoinQueue},
};

use crate::bstream::UtpStream;
use crate::conn::{
    self, ConnectedRecv, Connection, Handshake, Incoming, OutgoingRecv, OutgoingSend,
};
use crate::error;
use crate::mtu::{self, PathMtuProber, PathMtuProberGuard};
use crate::timestamp;

#[derive(Debug)]
pub struct UtpSocket {
    socket: Arc<UdpSocket>,

    connect_send: ConnectSend,
    accept_recv: AcceptRecv,

    guard: JoinGuard<Result<(), Error>>,
}

#[derive(Clone, Debug)]
pub struct UtpConnector {
    socket: Arc<UdpSocket>,
    connect_send: ConnectSend,
}

#[derive(Clone, Debug)]
pub struct UtpListener {
    socket: Arc<UdpSocket>,
    accept_recv: AcceptRecv,
}

#[derive(Debug)]
struct Actor<UdpStream, UdpSink> {
    cancel: Cancel,

    socket: Arc<UdpSocket>,

    stream: UdpStream,
    sink: UdpSink,

    connect_recv: ConnectRecv,
    accept_send: AcceptSend,

    tasks: JoinQueue<Result<(), conn::Error>>,
    peer_endpoints: HashMap<Id, SocketAddr>,
    stubs: HashMap<SocketAddr, Connection>,
    outgoing_recv: OutgoingRecv,
    outgoing_send: OutgoingSend,

    prober: PathMtuProber,
    prober_task: PathMtuProberGuard,
}

g1_param::define!(connect_queue_size: usize = 64);
g1_param::define!(accept_queue_size: usize = 64);

type Connect = (SocketAddr, oneshot::Sender<Result<UtpStream, Error>>);
type ConnectRecv = mpsc::Receiver<Connect>;
type ConnectSend = mpsc::Sender<Connect>;

type AcceptRecv = mpmc::Receiver<UtpStream>;
type AcceptSend = mpmc::Sender<UtpStream>;

impl UtpSocket {
    pub fn new<UdpStream, UdpSink>(socket: Arc<UdpSocket>, stream: UdpStream, sink: UdpSink) -> Self
    where
        UdpStream: Stream<Item = Result<(SocketAddr, Bytes), Error>> + Send + Unpin + 'static,
        UdpSink: Sink<(SocketAddr, Bytes), Error = Error> + Send + Unpin + 'static,
    {
        let (connect_send, connect_recv) = mpsc::channel(*connect_queue_size());
        let (accept_send, accept_recv) = mpmc::channel(*accept_queue_size());
        let guard = {
            let socket = socket.clone();
            JoinGuard::spawn(move |cancel| {
                Actor::new(cancel, socket, stream, sink, connect_recv, accept_send).run()
            })
        };
        Self {
            socket,
            connect_send,
            accept_recv,
            guard,
        }
    }

    pub fn socket(&self) -> &UdpSocket {
        &self.socket
    }

    pub fn connector(&self) -> UtpConnector {
        UtpConnector::new(self.socket.clone(), self.connect_send.clone())
    }

    pub fn listener(&self) -> UtpListener {
        UtpListener::new(self.socket.clone(), self.accept_recv.clone())
    }

    pub async fn join(&mut self) {
        self.guard.join().await
    }

    pub async fn shutdown(&mut self) -> Result<(), Error> {
        self.guard.shutdown().await?
    }
}

impl UtpConnector {
    fn new(socket: Arc<UdpSocket>, connect_send: ConnectSend) -> Self {
        Self {
            socket,
            connect_send,
        }
    }

    pub fn socket(&self) -> &UdpSocket {
        &self.socket
    }

    pub async fn connect(&self, peer_endpoint: SocketAddr) -> Result<UtpStream, Error> {
        fn to_io_error<E>(_: E) -> Error {
            Error::new(ErrorKind::ConnectionAborted, error::Error::Shutdown)
        }
        let (result_send, result_recv) = oneshot::channel();
        self.connect_send
            .send((peer_endpoint, result_send))
            .await
            .map_err(to_io_error)?;
        result_recv.await.map_err(to_io_error)?
    }
}

impl UtpListener {
    fn new(socket: Arc<UdpSocket>, accept_recv: AcceptRecv) -> Self {
        Self {
            socket,
            accept_recv,
        }
    }

    pub fn socket(&self) -> &UdpSocket {
        &self.socket
    }

    pub async fn accept(&self) -> Result<UtpStream, Error> {
        self.accept_recv
            .recv()
            .await
            .ok_or_else(|| Error::new(ErrorKind::ConnectionAborted, error::Error::Shutdown))
    }
}

impl<UdpStream, UdpSink> Actor<UdpStream, UdpSink>
where
    UdpStream: Stream<Item = Result<(SocketAddr, Bytes), Error>> + Unpin + 'static,
    UdpSink: Sink<(SocketAddr, Bytes), Error = Error> + Unpin + 'static,
{
    fn new(
        cancel: Cancel,
        socket: Arc<UdpSocket>,
        stream: UdpStream,
        sink: UdpSink,
        connect_recv: ConnectRecv,
        accept_send: AcceptSend,
    ) -> Self {
        let (outgoing_recv, outgoing_send) = conn::new_outgoing_queue();

        // TODO: Handle `PathMtuProber::spawn` error.
        let (prober, prober_task) = PathMtuProber::spawn().unwrap();
        prober_task.add_parent(cancel.clone());

        Self {
            cancel: cancel.clone(),
            socket,
            stream,
            sink,
            connect_recv,
            accept_send,
            tasks: JoinQueue::with_cancel(cancel),
            peer_endpoints: HashMap::new(),
            stubs: HashMap::new(),
            outgoing_recv,
            outgoing_send,
            prober,
            prober_task,
        }
    }

    async fn run(mut self) -> Result<(), Error> {
        let result = try {
            loop {
                tokio::select! {
                    () = self.cancel.wait() => break,

                    connect = self.connect_recv.recv() => {
                        let Some((peer_endpoint, result_send)) = connect else {
                            // `UtpSocket` was dropped (which aborts the actor), and in this case,
                            // the actor should exit.
                            break;
                        };
                        self.handle_connect(peer_endpoint, result_send);
                    }
                    guard = self.tasks.join_next() => {
                        let peer_endpoint =
                            handle_conn_result(&mut self.peer_endpoints, guard.unwrap());
                        self.remove(peer_endpoint);
                    }
                    incoming = self.stream.try_next() => {
                        let recv_at = timestamp::now();
                        let (peer_endpoint, payload) = incoming?.ok_or_else(|| {
                            Error::new(ErrorKind::UnexpectedEof, error::Error::Closed)
                        })?;
                        self.handle_incoming(peer_endpoint, (payload, recv_at));
                    }
                    outgoing = self.outgoing_recv.recv() => {
                        let (peer_endpoint, mut packet) = outgoing.unwrap();
                        let mut buffer = BytesMut::with_capacity(packet.size());
                        packet.header.set_send_at(timestamp::now());
                        packet.encode(&mut buffer);
                        self.sink.send((peer_endpoint, buffer.freeze())).await?;
                    }
                    path_mtu = self.prober.path_mtu_recv.recv() => {
                        let Some((peer_endpoint, path_mtu)) = path_mtu else { break };
                        if let Some(stub) = self.stubs.get(&peer_endpoint) {
                            // Ignore the channel closed error.
                            let _ = stub.packet_size_send.send(mtu::to_packet_size(path_mtu));
                        }
                    }
                }
            }
        };

        // Drop `mpsc` channels to induce graceful shutdown in `Connection`.
        let Actor {
            tasks,
            mut peer_endpoints,
            mut prober_task,
            mut sink,
            ..
        } = self;
        tokio::join!(
            async move {
                tasks.cancel();
                while let Some(guard) = tasks.join_next().await {
                    handle_conn_result(&mut peer_endpoints, guard);
                }
            },
            async move {
                if let Err(error) = prober_task.shutdown().await {
                    tracing::warn!(%error, "path mtu prober task error");
                }
            },
            async move {
                if let Err(error) = sink.close().await {
                    tracing::warn!(%error, "udp sink close error");
                }
            }
        );

        result
    }

    #[tracing::instrument("utp/connect", fields(?peer_endpoint), skip_all)]
    fn handle_connect(
        &mut self,
        peer_endpoint: SocketAddr,
        result_send: oneshot::Sender<Result<UtpStream, Error>>,
    ) {
        if self.stubs.contains_key(&peer_endpoint) {
            let _ = result_send.send(Err(Error::new(
                ErrorKind::AddrInUse,
                error::Error::Duplicated { peer_endpoint },
            )));
            return;
        }
        let (stream, connected_recv) = self.spawn(peer_endpoint, Handshake::new_connect);
        tokio::spawn(Self::handle_connected(
            peer_endpoint,
            stream,
            connected_recv,
            self.prober.probe_send.clone(),
            result_send,
        ));
    }

    #[tracing::instrument("utp/connect", fields(?peer_endpoint), skip_all)]
    async fn handle_connected(
        peer_endpoint: SocketAddr,
        stream: UtpStream,
        connected_recv: ConnectedRecv,
        probe_send: mpsc::Sender<SocketAddr>,
        result_send: oneshot::Sender<Result<UtpStream, Error>>,
    ) {
        let result = match connected_recv.await {
            Ok(Ok(())) => {
                if matches!(
                    probe_send.try_send(peer_endpoint),
                    Err(mpsc::error::TrySendError::Full(_)),
                ) {
                    tracing::warn!("path mtu prober queue is full");
                }
                Ok(stream)
            }
            Ok(Err(error)) => Err(error),
            Err(_) => Err(Error::new(
                ErrorKind::ConnectionAborted,
                error::Error::Handshake { peer_endpoint },
            )),
        };
        let _ = result_send.send(result);
    }

    #[tracing::instrument("utp/accept", fields(?peer_endpoint), skip_all)]
    fn handle_accept(&mut self, peer_endpoint: SocketAddr) {
        let (stream, connected_recv) = self.spawn(peer_endpoint, Handshake::new_accept);
        tokio::spawn(Self::handle_accepted(
            peer_endpoint,
            stream,
            connected_recv,
            self.prober.probe_send.clone(),
            self.accept_send.clone(),
        ));
    }

    #[tracing::instrument("utp/accept", fields(?peer_endpoint), skip_all)]
    async fn handle_accepted(
        peer_endpoint: SocketAddr,
        stream: UtpStream,
        connected_recv: ConnectedRecv,
        probe_send: mpsc::Sender<SocketAddr>,
        accept_send: AcceptSend,
    ) {
        if matches!(connected_recv.await, Ok(Ok(()))) {
            if matches!(
                probe_send.try_send(peer_endpoint),
                Err(mpsc::error::TrySendError::Full(_)),
            ) {
                tracing::warn!("path mtu prober queue is full");
            }
            if matches!(
                accept_send.try_send(stream),
                Err(mpmc::error::TrySendError::Full(_)),
            ) {
                tracing::warn!("utp accept queue is full");
            }
            // Dropping `stream` causes connection actor to exit.
        }
    }

    fn handle_incoming(&mut self, peer_endpoint: SocketAddr, incoming: Incoming) {
        if !self.stubs.contains_key(&peer_endpoint) {
            self.handle_accept(peer_endpoint);
        }

        let span = tracing::info_span!("utp/incoming", ?peer_endpoint);
        let _guard = span.enter();

        let stub = self.stubs.get(&peer_endpoint).unwrap();
        if let Err(error) = stub.incoming_send.try_send(incoming) {
            if matches!(error, mpsc::error::TrySendError::Full(_)) {
                tracing::warn!("utp connection incoming queue is full");
            }
            self.remove(peer_endpoint);
        }
    }

    fn spawn(
        &mut self,
        peer_endpoint: SocketAddr,
        new_handshake: fn() -> Handshake,
    ) -> (UtpStream, ConnectedRecv) {
        let (connected_send, connected_recv) = oneshot::channel();
        let (stub, guard, stream) = conn::Connection::spawn(
            new_handshake(),
            self.socket.clone(),
            peer_endpoint,
            connected_send,
            self.outgoing_send.clone(),
        );
        let id = guard.id();
        self.tasks.push(guard).unwrap();
        assert!(self.peer_endpoints.insert(id, peer_endpoint).is_none());
        assert!(self.stubs.insert(peer_endpoint, stub).is_none());
        (stream, connected_recv)
    }

    fn remove(&mut self, peer_endpoint: SocketAddr) {
        self.stubs.remove(&peer_endpoint);
    }
}

fn handle_conn_result(
    peer_endpoints: &mut HashMap<Id, SocketAddr>,
    mut guard: JoinGuard<Result<(), conn::Error>>,
) -> SocketAddr {
    let peer_endpoint = peer_endpoints.remove(&guard.id()).unwrap();
    match guard.take_result() {
        Ok(Ok(())) => {}
        Ok(Err(error)) => {
            if error == conn::Error::ConnectTimeout {
                tracing::debug!(?peer_endpoint, "utp connect timeout");
            } else {
                tracing::warn!(?peer_endpoint, %error, "utp connection error");
            }
        }
        Err(error) => tracing::warn!(?peer_endpoint, %error, "utp connection shutdown error"),
    }
    peer_endpoint
}
