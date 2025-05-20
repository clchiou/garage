use std::io;
use std::time::Duration;

use futures::future::OptionFuture;
use futures::sink::SinkExt;
use futures::stream::StreamExt;
use snafu::prelude::*;
use tokio::sync::{mpsc, oneshot, watch};
use tokio::time::{self, Instant};
use zmq::{Context, DEALER};

use g1_base::fmt::{DebugExt, InsertPlaceholder};
use g1_tokio::task::Cancel;
use g1_zmq::Socket;
use g1_zmq::duplex::Duplex;
use g1_zmq::envelope::{Envelope, Frame, Multipart};

use ddcache_rpc::envelope;
use ddcache_rpc::service::Server;

use crate::error::{
    DecodeSnafu, Error, InvalidResponseSnafu, InvalidRoutingIdSnafu, ResponseError,
};
use crate::response::{Response, ResponseResult, ResponseSend, ResponseSends, RoutingId};

#[derive(DebugExt)]
pub(crate) struct Actor {
    cancel: Cancel,
    server_recv: ServerRecv,
    request_recv: RequestRecv,
    response_sends: ResponseSends,
    #[debug(with = InsertPlaceholder)]
    context: Context,
}

pub(crate) type ServerRecv = watch::Receiver<Server>;
pub(crate) type ServerSend = watch::Sender<Server>;

pub(crate) type Request = (ddcache_rpc::Request, ResponseSend);
pub(crate) type RequestRecv = mpsc::Receiver<Request>;
pub(crate) type RequestSend = mpsc::Sender<Request>;

impl Actor {
    pub(crate) fn new(cancel: Cancel, server_recv: ServerRecv, request_recv: RequestRecv) -> Self {
        Self {
            cancel,
            server_recv,
            request_recv,
            response_sends: ResponseSends::new(),
            context: Context::new(),
        }
    }

    pub(crate) async fn run(mut self) -> Result<(), io::Error> {
        let mut duplex = self.connect().await?;

        let mut deadline = None;
        tokio::pin! { let timeout = OptionFuture::from(None); }

        let mut idle_interval = time::interval(Duration::from_secs(120));
        let mut keepalive_response_recv = None;

        idle_interval.reset();
        loop {
            let next_deadline = self.response_sends.next_deadline();
            if deadline != next_deadline {
                deadline = next_deadline;
                timeout.set(deadline.map(time::sleep_until).into());
            }

            tokio::select! {
                () = self.cancel.wait() => break,

                changed = self.server_recv.changed() => {
                    if changed.is_err() {
                        break;
                    }
                    duplex = self.connect().await?;
                }

                request = self.request_recv.recv() => {
                    let Some(request) = request else { break };
                    // Block the actor loop on `duplex.send` because it is probably desirable to
                    // derive back pressure from this point.
                    self.handle_request(request, &mut duplex).await;

                    idle_interval.reset();
                }

                response = duplex.next() => {
                    // We assume that errors below are transient and do not exit.
                    match response {
                        Some(Ok(response)) => {
                            if let Err(error) = self.handle_response(response) {
                                tracing::warn!(%error, "response");
                            }
                        }
                        Some(Err(error)) => tracing::warn!(%error, "recv"),
                        None => break,
                    }
                }

                Some(()) = &mut timeout => {
                    self.response_sends.remove_expired(Instant::now());
                    deadline = None;
                    timeout.set(None.into());
                }

                _ = idle_interval.tick() => {
                    tracing::debug!("idle timeout");
                    keepalive_response_recv = Some(self.send_keepalive(&mut duplex).await);
                }
                Some(response) = OptionFuture::from(keepalive_response_recv.as_mut()) => {
                    match response.unwrap() {
                        Ok(Some(response)) => {
                            tracing::warn!(?response, "unexpected keepalive response");
                        }
                        Ok(None) => {}
                        Err(error) => tracing::warn!(%error, "keepalive"),
                    }
                    keepalive_response_recv = None;
                }
            }
        }

        Ok(())
    }

    async fn connect(&mut self) -> Result<Duplex, io::Error> {
        let server = self.server_recv.borrow_and_update().clone();
        tracing::info!(?server, "connect");

        let mut socket = Socket::try_from(self.context.socket(DEALER)?)?;
        socket.set_linger(0)?; // Do NOT block the program exit!

        // TODO: Try each endpoint of the target server, as some of them may be unreachable from
        // our end.
        socket.connect(&server.endpoints[0])?;

        Ok(socket.into())
    }

    async fn send_keepalive(&mut self, duplex: &mut Duplex) -> oneshot::Receiver<ResponseResult> {
        // Send `cancel(0)` as keep-alive messages.
        let (response_send, response_recv) = oneshot::channel();
        self.handle_request((ddcache_rpc::Request::Cancel(0), response_send), duplex)
            .await;
        response_recv
    }

    async fn handle_request(&mut self, (request, response_send): Request, duplex: &mut Duplex) {
        tracing::debug!(?request);
        let routing_id = self.response_sends.insert(response_send);
        let request = Envelope::new(
            vec![Frame::from(routing_id.to_be_bytes().as_slice())],
            Frame::from(Vec::<u8>::from(request)),
        );
        // We assume that this error is transient and do not exit.
        // TODO: Should we re-send the request?
        if let Err(error) = duplex.send(request.into()).await {
            tracing::warn!(%error, "send");
            let _ = self
                .response_sends
                .remove(routing_id)
                .unwrap()
                .send(Err(Error::Request { source: error }));
        }
    }

    fn handle_response(&mut self, frames: Multipart) -> Result<(), ResponseError> {
        let response = envelope::decode(frames).context(InvalidResponseSnafu)?;

        let routing_id = response.routing_id();
        ensure!(
            routing_id.len() == 1 && routing_id[0].len() == 8,
            InvalidRoutingIdSnafu { response },
        );
        let routing_id = RoutingId::from_be_bytes((*routing_id[0]).try_into().unwrap());

        let response = Self::decode(response);
        tracing::debug!(?response);

        let Some(response_send) = self.response_sends.remove(routing_id) else {
            tracing::debug!(routing_id, "response_send not found");
            return Ok(());
        };

        let _ = response_send.send(response);
        Ok(())
    }

    fn decode(response: Envelope<Frame>) -> ResponseResult {
        let result: Result<_, capnp::Error> = try {
            match **envelope::decode_response(response)?.data() {
                Ok(Some(response)) => Ok(Response::try_from(response)?),
                Ok(None) => Ok(None),
                Err(error) => Err(Error::try_from(error)?),
            }
        };
        result.context(DecodeSnafu)?
    }
}
