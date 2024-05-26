use std::collections::HashMap;
use std::io;

use futures::future::OptionFuture;
use futures::sink::SinkExt;
use futures::stream::StreamExt;
use snafu::prelude::*;
use tokio::sync::{mpsc, oneshot, watch};
use tokio::time;
use zmq::{Context, DEALER};

use g1_base::fmt::{DebugExt, InsertPlaceholder};
use g1_tokio::task::Cancel;
use g1_tokio::time::queue::naive::FixedDelayQueue;
use g1_zmq::duplex::Duplex;
use g1_zmq::envelope::{Envelope, Frame, Multipart};
use g1_zmq::Socket;

use dkvcache_rpc::envelope;
use dkvcache_rpc::service::Server;
use dkvcache_rpc::{Request, ResponseResultExt};

use crate::error::{
    DecodeSnafu, Error, InvalidResponseSnafu, InvalidRoutingIdSnafu, ResponseError, RpcSnafu,
};
use crate::ResponseResult;

#[derive(DebugExt)]
pub(crate) struct Actor {
    cancel: Cancel,

    server_recv: ServerRecv,
    request_recv: RequestRecv,

    #[debug(with = InsertPlaceholder)]
    context: Context,

    map: HashMap<RoutingId, ResponseSend>,
    expire_queue: FixedDelayQueue<RoutingId>,
}

pub(crate) type ServerRecv = watch::Receiver<Server>;
pub(crate) type ServerSend = watch::Sender<Server>;

pub(crate) type RoutingId = u64;

pub(crate) type ReqRep = (Request, ResponseSend);
pub(crate) type RequestRecv = mpsc::Receiver<ReqRep>;
pub(crate) type RequestSend = mpsc::Sender<ReqRep>;

pub(crate) type ResponseSend = oneshot::Sender<ResponseResult>;
pub(crate) type ResponseRecv = oneshot::Receiver<ResponseResult>;

impl Actor {
    pub(crate) fn new(cancel: Cancel, server_recv: ServerRecv, request_recv: RequestRecv) -> Self {
        Self {
            cancel,

            server_recv,
            request_recv,

            context: Context::new(),

            map: HashMap::new(),
            expire_queue: FixedDelayQueue::new(*crate::request_timeout()),
        }
    }

    pub(crate) async fn run(mut self) -> Result<(), io::Error> {
        let mut duplex = self.connect().await?;

        let mut idle_interval = time::interval(*crate::idle_timeout());
        let mut keepalive_response_recv = None;

        idle_interval.reset();
        loop {
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

                Some(routing_id) = self.expire_queue.pop() => {
                    self.handle_expire(routing_id);
                }

                _ = idle_interval.tick() => {
                    tracing::info!("idle timeout");
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

    async fn send_keepalive(&mut self, duplex: &mut Duplex) -> ResponseRecv {
        let (response_send, response_recv) = oneshot::channel();
        self.handle_request((Request::Ping, response_send), duplex)
            .await;
        response_recv
    }

    async fn handle_request(&mut self, (request, response_send): ReqRep, duplex: &mut Duplex) {
        tracing::debug!(?request);

        let routing_id = self.next_routing_id();
        assert!(self.map.insert(routing_id, response_send).is_none());
        self.expire_queue.push(routing_id);

        let request = Envelope::new(
            vec![Frame::from(routing_id.to_be_bytes().as_slice())],
            Frame::from(Vec::<u8>::from(request)),
        );

        // We assume that this error is transient and do not exit.
        // TODO: Should we re-send the request?
        if let Err(error) = duplex.send(request.into()).await {
            tracing::warn!(%error, "send");
            let _ = self
                .map
                .remove(&routing_id)
                .unwrap()
                .send(Err(Error::Request { source: error }));
        }
    }

    fn next_routing_id(&self) -> RoutingId {
        for _ in 0..4 {
            let routing_id = rand::random();
            // It is a small detail, but we do not generate 0.
            if routing_id != 0 && !self.map.contains_key(&routing_id) {
                return routing_id;
            }
        }
        std::panic!("cannot generate random routing id")
    }

    fn handle_response(&mut self, frames: Multipart) -> Result<(), ResponseError> {
        let response = envelope::decode(frames).context(InvalidResponseSnafu)?;

        let routing_id = response.routing_id();
        ensure!(
            routing_id.len() == 1 && routing_id[0].len() == 8,
            InvalidRoutingIdSnafu { response },
        );
        let routing_id = RoutingId::from_be_bytes((*routing_id[0]).try_into().unwrap());

        let response = dkvcache_rpc::ResponseResult::decode(response.data())
            .context(DecodeSnafu)
            .and_then(|result| result.context(RpcSnafu));
        tracing::debug!(?response);

        let Some(response_send) = self.map.remove(&routing_id) else {
            tracing::debug!(routing_id, "response_send not found");
            return Ok(());
        };

        let _ = response_send.send(response);
        Ok(())
    }

    fn handle_expire(&mut self, routing_id: RoutingId) {
        if let Some(response_send) = self.map.remove(&routing_id) {
            tracing::warn!(routing_id, "expire");
            let _ = response_send.send(Err(Error::RequestTimeout));
        }
    }
}
