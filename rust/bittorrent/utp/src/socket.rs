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
    sync::{
        mpsc::{self, error::TrySendError, Receiver, Sender},
        oneshot, Mutex,
    },
    task::{Id, JoinError, JoinHandle},
    time,
};
use tracing::Instrument;

use g1_tokio::task::{self, JoinQueue, JoinTaskError};

use crate::bstream::UtpStream;
use crate::conn::{
    self, ActorStub, ConnectedRecv, Handshake, Incoming, OutgoingRecv, OutgoingSend,
};
use crate::mtu::{self, PathMtuProber};
use crate::timestamp;

#[derive(Debug)]
pub struct UtpSocket {
    socket: Arc<UdpSocket>,

    connect_send: ConnectSend,
    accept_recv: Mutex<AcceptRecv>,

    conn_tasks: JoinQueue<Result<(), conn::Error>>,

    task: Mutex<JoinHandle<Result<(), Error>>>,
}

#[derive(Debug)]
struct Actor<UdpStream, UdpSink> {
    socket: Arc<UdpSocket>,

    stream: UdpStream,
    sink: UdpSink,

    connect_recv: ConnectRecv,
    accept_send: AcceptSend,

    conn_tasks: JoinQueue<Result<(), conn::Error>>,
    peer_endpoints: HashMap<Id, SocketAddr>,
    stubs: HashMap<SocketAddr, ActorStub>,
    outgoing_recv: OutgoingRecv,
    outgoing_send: OutgoingSend,

    prober: PathMtuProber,
}

g1_param::define!(connect_queue_size: usize = 64);
g1_param::define!(accept_queue_size: usize = 64);

type Connect = (SocketAddr, oneshot::Sender<Result<UtpStream, Error>>);
type ConnectRecv = Receiver<Connect>;
type ConnectSend = Sender<Connect>;

type AcceptRecv = Receiver<UtpStream>;
type AcceptSend = Sender<UtpStream>;

impl UtpSocket {
    pub fn new<UdpStream, UdpSink>(socket: Arc<UdpSocket>, stream: UdpStream, sink: UdpSink) -> Self
    where
        UdpStream: Stream<Item = Result<(SocketAddr, Bytes), Error>> + Send + Unpin + 'static,
        UdpSink: Sink<(SocketAddr, Bytes), Error = Error> + Send + Unpin + 'static,
    {
        let (connect_send, connect_recv) = mpsc::channel(*connect_queue_size());
        let (accept_send, accept_recv) = mpsc::channel(*accept_queue_size());
        let conn_tasks = JoinQueue::new();
        let actor = Actor::new(
            socket.clone(),
            stream,
            sink,
            connect_recv,
            accept_send,
            conn_tasks.clone(),
        );
        Self {
            socket,
            connect_send,
            accept_recv: Mutex::new(accept_recv),
            conn_tasks,
            task: Mutex::new(tokio::spawn(actor.run())),
        }
    }

    pub fn socket(&self) -> &UdpSocket {
        &self.socket
    }

    pub async fn connect(&self, peer_endpoint: SocketAddr) -> Result<UtpStream, Error> {
        fn to_io_error<E>(_: E) -> Error {
            Error::new(ErrorKind::ConnectionAborted, "utp socket is shutting down")
        }
        let (result_send, result_recv) = oneshot::channel();
        self.connect_send
            .send((peer_endpoint, result_send))
            .await
            .map_err(to_io_error)?;
        result_recv.await.map_err(to_io_error)?
    }

    pub async fn accept(&self) -> Result<UtpStream, Error> {
        self.accept_recv
            .lock()
            .await
            .recv()
            .await
            .ok_or_else(|| Error::new(ErrorKind::ConnectionAborted, "utp socket is shutting down"))
    }

    pub async fn shutdown(&self) -> Result<(), Error> {
        self.conn_tasks.close();
        task::join_task(&self.task, *crate::grace_period())
            .await
            .map_err(|error| match error {
                JoinTaskError::Cancelled => Error::other("utp socket actor is cancelled"),
                JoinTaskError::Timeout => Error::new(
                    ErrorKind::TimedOut,
                    "utp socket shutdown grace period is exceeded",
                ),
            })?
    }
}

impl Drop for UtpSocket {
    fn drop(&mut self) {
        self.conn_tasks.abort_all();
        self.task.get_mut().abort();
    }
}

impl<UdpStream, UdpSink> Actor<UdpStream, UdpSink>
where
    UdpStream: Stream<Item = Result<(SocketAddr, Bytes), Error>> + Unpin,
    UdpSink: Sink<(SocketAddr, Bytes), Error = Error> + Unpin,
{
    fn new(
        socket: Arc<UdpSocket>,
        stream: UdpStream,
        sink: UdpSink,
        connect_recv: ConnectRecv,
        accept_send: AcceptSend,
        conn_tasks: JoinQueue<Result<(), conn::Error>>,
    ) -> Self {
        let (outgoing_recv, outgoing_send) = conn::new_outgoing_queue();
        Self {
            socket,
            stream,
            sink,
            connect_recv,
            accept_send,
            conn_tasks,
            peer_endpoints: HashMap::new(),
            stubs: HashMap::new(),
            outgoing_recv,
            outgoing_send,
            prober: PathMtuProber::new(*crate::path_mtu_reprobe_period()).unwrap(),
        }
    }

    async fn run(mut self) -> Result<(), Error> {
        let result = try {
            loop {
                tokio::select! {
                    connect = self.connect_recv.recv() => {
                        match connect {
                            Some((peer_endpoint, result_send)) => {
                                self.connect(peer_endpoint, result_send);
                            }
                            // `UtpSocket` was dropped (which aborts the actor), and in this case,
                            // the actor should exit.
                            None => break,
                        }
                    }
                    join_result = self.conn_tasks.join_next_with_id() => {
                        match join_result {
                            Some(join_result) => {
                                let peer_endpoint =
                                    join_conn_actor(&mut self.peer_endpoints, join_result);
                                self.remove(peer_endpoint);
                            }
                            None => break, // `UtpSocket::shutdown` was called.
                        }
                    }
                    incoming = self.stream.try_next() => {
                        let recv_at = timestamp::now();
                        let (peer_endpoint, payload) = incoming?.ok_or_else(|| {
                            Error::new(
                                ErrorKind::UnexpectedEof,
                                "the underlying udp socket is closed",
                            )
                        })?;
                        self.incoming_send(peer_endpoint, (payload, recv_at));
                    }
                    outgoing = self.outgoing_recv.recv() => {
                        let (peer_endpoint, mut packet) = outgoing.unwrap();
                        let mut buffer = BytesMut::with_capacity(packet.size());
                        packet.header.set_send_at(timestamp::now());
                        packet.encode(&mut buffer);
                        self.sink.send((peer_endpoint, buffer.freeze())).await?;
                    }
                    Some((peer_endpoint, path_mtu)) = self.prober.next() => {
                        if let Some(stub) = self.stubs.get(&peer_endpoint) {
                            // Ignore the channel closed error.
                            let _ = stub.packet_size_send.send(mtu::to_packet_size(path_mtu));
                        }
                    }
                }
            }
        };

        // Drop `mpsc` channels to induce graceful shutdown in `conn::Actor`.
        let Actor {
            conn_tasks,
            mut peer_endpoints,
            ..
        } = self;
        conn_tasks.close();
        let _ = time::timeout(*crate::grace_period() / 2, async {
            while let Some(join_result) = conn_tasks.join_next_with_id().await {
                join_conn_actor(&mut peer_endpoints, join_result);
            }
        })
        .await;
        conn_tasks.abort_all_then_join().await;

        result
    }

    fn connect(
        &mut self,
        peer_endpoint: SocketAddr,
        result_send: oneshot::Sender<Result<UtpStream, Error>>,
    ) {
        // Unfortunately, the borrow checker disallows the use of `HashMap::entry` because we call
        // methods (which also borrow `self`) while holding the entry.
        if self.stubs.contains_key(&peer_endpoint) {
            let _ = result_send.send(Err(Error::new(
                ErrorKind::AddrInUse,
                format!("duplicated utp connections: {}", peer_endpoint),
            )));
            return;
        }
        if let Some((stream, connected_recv)) = self.spawn(peer_endpoint, Handshake::new_connect) {
            tokio::spawn(async move {
                let _ = result_send.send(match connected_recv.await {
                    Ok(result) => result.map(|()| stream),
                    Err(_) => Err(Error::new(
                        ErrorKind::ConnectionAborted,
                        "utp handshake error",
                    )),
                });
            });
        }
        // Dropping `result_send` causes `UtpSocket::connect` to return a `BrokenPipe` error.
    }

    fn accept(&mut self, peer_endpoint: SocketAddr) -> bool {
        match self.spawn(peer_endpoint, Handshake::new_accept) {
            Some((stream, connected_recv)) => {
                let accept_send = self.accept_send.clone();
                tokio::spawn(async move {
                    if let Ok(Ok(())) = connected_recv.await {
                        if let Err(TrySendError::Full(_)) = accept_send.try_send(stream) {
                            tracing::warn!("utp accept queue is full");
                        }
                        // Dropping `stream` causes connection actor to exit.
                    }
                });
                true
            }
            None => false,
        }
    }

    fn incoming_send(&mut self, peer_endpoint: SocketAddr, incoming: Incoming) {
        // We cannot use `HashMap::entry` for the same reason as above.
        if !self.stubs.contains_key(&peer_endpoint) && !self.accept(peer_endpoint) {
            let (payload, _) = incoming;
            tracing::debug!(
                ?peer_endpoint,
                ?payload,
                "drop incoming packet because utp socket is shutting down",
            );
            return;
        }
        let stub = self.stubs.get(&peer_endpoint).unwrap();
        if let Err(error) = stub.incoming_send.try_send(incoming) {
            if matches!(error, TrySendError::Full(_)) {
                tracing::warn!(?peer_endpoint, "utp connection incoming queue is full");
            }
            self.remove(peer_endpoint);
        }
    }

    fn spawn(
        &mut self,
        peer_endpoint: SocketAddr,
        new_handshake: fn() -> Handshake,
    ) -> Option<(UtpStream, ConnectedRecv)> {
        let (connected_send, connected_recv) = oneshot::channel();
        let ((actor, stub), stream) = conn::Actor::with_socket(
            new_handshake(),
            self.socket.clone(),
            peer_endpoint,
            connected_send,
            self.outgoing_send.clone(),
        );
        let actor_run = actor
            .run()
            .instrument(tracing::info_span!("utp/conn", ?peer_endpoint));
        match self.conn_tasks.spawn(actor_run) {
            Ok(handle) => {
                assert!(self
                    .peer_endpoints
                    .insert(handle.id(), peer_endpoint)
                    .is_none());
                assert!(self.stubs.insert(peer_endpoint, stub).is_none());
                self.prober.register(peer_endpoint);
                Some((stream, connected_recv))
            }
            Err(handle) => {
                handle.abort();
                None
            }
        }
    }

    fn remove(&mut self, peer_endpoint: SocketAddr) {
        self.stubs.remove(&peer_endpoint);
        self.prober.unregister(&peer_endpoint);
    }
}

fn join_conn_actor(
    peer_endpoints: &mut HashMap<Id, SocketAddr>,
    join_result: Result<(Id, Result<(), conn::Error>), JoinError>,
) -> SocketAddr {
    match join_result {
        Ok((id, result)) => {
            let peer_endpoint = peer_endpoints.remove(&id).unwrap();
            if let Err(error) = result {
                if error == conn::Error::ConnectTimeout {
                    tracing::debug!(?peer_endpoint, ?error, "utp connect timeout");
                } else {
                    tracing::warn!(?peer_endpoint, ?error, "utp connection actor error");
                }
            }
            peer_endpoint
        }
        Err(join_error) => {
            if join_error.is_panic() {
                panic::resume_unwind(join_error.into_panic());
            }
            assert!(join_error.is_cancelled());
            let peer_endpoint = peer_endpoints.remove(&join_error.id()).unwrap();
            tracing::warn!(?peer_endpoint, "utp connection actor is cancelled");
            peer_endpoint
        }
    }
}
