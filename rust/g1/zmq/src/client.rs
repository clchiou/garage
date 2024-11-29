//! It is unfortunate that the [client] pattern is still in draft state.  We have to implement it
//! ourselves for the time being.
//!
//! [client]: https://zeromq.org/socket-api/#client-server-pattern

use std::collections::HashMap;
use std::io::{Error, ErrorKind};
use std::sync::Arc;
use std::time::Duration;

use bytes::Bytes;
use futures::sink::SinkExt;
use futures::stream::StreamExt;
use tokio::sync::mpsc;
use tokio::sync::oneshot;

use g1_tokio::task::{Cancel, JoinGuard};
use g1_tokio::time::queue::naive::FixedDelayQueue;

use crate::duplex::Duplex;
use crate::envelope::{Envelope, Frame, Multipart};
use crate::Socket;

#[cfg(feature = "param")]
mod param {
    use std::io::Error;
    use std::time::Duration;

    use serde::Deserialize;

    use crate::{Dealer, SocketBuilder};

    use super::{Client, ClientGuard};

    #[derive(Clone, Debug, Deserialize)]
    #[serde(default, deny_unknown_fields)]
    pub struct ClientBuilder {
        pub socket: SocketBuilder<Dealer>,
        #[serde(deserialize_with = "de::duration")]
        pub timeout: Duration,
    }

    impl Default for ClientBuilder {
        fn default() -> Self {
            Self {
                socket: Default::default(),
                timeout: Duration::from_secs(2),
            }
        }
    }

    impl ClientBuilder {
        pub fn socket(&mut self) -> &mut SocketBuilder<Dealer> {
            &mut self.socket
        }

        pub fn timeout(&mut self, timeout: Duration) -> &mut Self {
            self.timeout = timeout;
            self
        }

        pub fn build(&self, context: &zmq::Context) -> Result<(Client, ClientGuard), Error> {
            if self.socket.bind.is_empty() && self.socket.connect.is_empty() {
                // When a `DEALER` socket has no peers, `send` will block.  This is probably not
                // what you want, so we return an error for now.
                return Err(Error::other("neither bind nor connect to any endpoints"));
            }
            let (socket, bind_endpoints) = self.socket.build(context)?;
            Ok(Client::spawn(
                socket.try_into()?,
                bind_endpoints,
                self.timeout,
            ))
        }
    }

    mod de {
        use std::time::Duration;

        use serde::de::{Deserializer, Error};
        use serde::Deserialize;

        use g1_param::parse;

        pub(super) fn duration<'de, D>(deserializer: D) -> Result<Duration, D::Error>
        where
            D: Deserializer<'de>,
        {
            // It seems nice to reuse `g1_param::parse::duration` here.
            parse::duration(<String>::deserialize(deserializer)?).map_err(D::Error::custom)
        }
    }
}

#[cfg(feature = "param")]
pub use self::param::ClientBuilder;

#[derive(Clone, Debug)]
pub struct Client {
    bind_endpoints: Arc<[String]>,
    request_send: RequestSend,
}

// For convenience, we make `Actor::run` return `Result<(), Error>`.
pub type ClientGuard = JoinGuard<Result<(), Error>>;

#[derive(Debug)]
struct Actor {
    cancel: Cancel,
    duplex: Duplex,
    request_recv: RequestRecv,
    response_sends: HashMap<RoutingId, ResponseSend>,
    deadlines: FixedDelayQueue<RoutingId>,
}

type RoutingId = u64;

type Request = (Bytes, ResponseSend);
type Response = Result<Bytes, Error>;

type RequestRecv = mpsc::Receiver<Request>;
type RequestSend = mpsc::Sender<Request>;

type ResponseSend = oneshot::Sender<Response>;

impl Client {
    fn spawn(
        socket: Socket,
        bind_endpoints: Vec<String>,
        timeout: Duration,
    ) -> (Self, ClientGuard) {
        let (request_send, request_recv) = mpsc::channel(32);
        let guard = ClientGuard::spawn(move |cancel| {
            Actor::new(cancel, socket, request_recv, timeout).run()
        });
        (
            Self {
                bind_endpoints: bind_endpoints.into(),
                request_send,
            },
            guard,
        )
    }

    pub fn bind_endpoints(&self) -> &[String] {
        &self.bind_endpoints
    }

    pub async fn request(&self, request: Bytes) -> Result<Bytes, Error> {
        fn stopped() -> Error {
            Error::other("client task stopped")
        }

        let (response_send, response_recv) = oneshot::channel();
        self.request_send
            .send((request, response_send))
            .await
            .map_err(|_| stopped())?;
        response_recv.await.map_err(|_| stopped())?
    }
}

impl Actor {
    fn new(cancel: Cancel, socket: Socket, request_recv: RequestRecv, timeout: Duration) -> Self {
        Self {
            cancel,
            duplex: socket.into(),
            request_recv,
            response_sends: HashMap::new(),
            deadlines: FixedDelayQueue::new(timeout),
        }
    }

    fn next_routing_id(&self) -> RoutingId {
        for _ in 0..4 {
            let routing_id = rand::random();
            // It is a small detail, but we do not generate 0.
            if routing_id != 0 && !self.response_sends.contains_key(&routing_id) {
                return routing_id;
            }
        }
        std::panic!("cannot generate random routing id")
    }

    fn insert(&mut self, response_send: ResponseSend) -> RoutingId {
        let routing_id = self.next_routing_id();
        assert!(self
            .response_sends
            .insert(routing_id, response_send)
            .is_none());
        self.deadlines.push(routing_id);
        routing_id
    }

    async fn run(mut self) -> Result<(), Error> {
        loop {
            tokio::select! {
                () = self.cancel.wait() => break,

                request = self.request_recv.recv() => {
                    let Some(request) = request else { break };
                    self.handle_request(request).await;
                }

                response = self.duplex.next() => {
                    match response {
                        Some(Ok(response)) => self.handle_response(response),
                        // We assume that this error is transient and do not exit.
                        Some(Err(error)) => tracing::warn!(%error, "recv"),
                        None => break,
                    }
                }

                Some(routing_id) = self.deadlines.pop() => {
                    self.handle_timeout(routing_id);
                }
            }
        }
        Ok(())
    }

    async fn handle_request(&mut self, (request, response_send): Request) {
        let routing_id = self.insert(response_send);
        tracing::trace!(routing_id, ?request);
        let request = Envelope::new(
            vec![Frame::from(routing_id.to_be_bytes().as_slice())],
            Frame::from(<Vec<u8>>::from(request)),
        );
        // We assume that this error is transient and do not exit.
        // TODO: Should we re-send the request?
        if let Err(error) = self.duplex.send(request.into()).await {
            let _ = self
                .response_sends
                .remove(&routing_id)
                .expect("response_send")
                .send(Err(error));
        }
    }

    fn handle_response(&mut self, frames: Multipart) {
        let envelope = match <Envelope<Frame>>::try_from(frames) {
            Ok(envelope) => envelope,
            Err(frames) => {
                tracing::warn!(?frames, "invalid frames");
                return;
            }
        };

        let routing_id = envelope.routing_id();
        if !(routing_id.len() == 1 && routing_id[0].len() == 8) {
            tracing::warn!(?envelope, "invalid routing id");
            return;
        }
        let routing_id = RoutingId::from_be_bytes((*routing_id[0]).try_into().expect("routing_id"));

        let (_, response) = envelope.unwrap();
        tracing::trace!(routing_id, ?response);

        let Some(response_send) = self.response_sends.remove(&routing_id) else {
            tracing::debug!(routing_id, "response_send not found");
            return;
        };

        let _ = response_send.send(Ok(response.to_vec().into()));
    }

    fn handle_timeout(&mut self, routing_id: RoutingId) {
        if let Some(response_send) = self.response_sends.remove(&routing_id) {
            let _ = response_send.send(Err(Error::new(ErrorKind::TimedOut, "request timeout")));
        }
    }
}
