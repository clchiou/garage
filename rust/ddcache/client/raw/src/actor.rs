use std::io;

use futures::future::OptionFuture;
use futures::sink::SinkExt;
use futures::stream::TryStreamExt;
use snafu::prelude::*;
use tokio::sync::mpsc;
use tokio::time::{self, Instant};

use g1_tokio::task::Cancel;
use g1_zmq::duplex::Duplex;
use g1_zmq::envelope::{Envelope, Frame, Multipart};

use ddcache_rpc::envelope;

use crate::error::{DecodeSnafu, Error, InvalidResponseSnafu, InvalidRoutingIdSnafu};
use crate::response::{Response, ResponseResult, ResponseSend, ResponseSends, RoutingId};

#[derive(Debug)]
pub(crate) struct Actor {
    cancel: Cancel,
    request_recv: RequestRecv,
    response_sends: ResponseSends,
    duplex: Duplex,
}

pub(crate) type Request = (ddcache_rpc::Request, ResponseSend);
pub(crate) type RequestRecv = mpsc::Receiver<Request>;
pub(crate) type RequestSend = mpsc::Sender<Request>;

impl Actor {
    pub(crate) fn new(cancel: Cancel, request_recv: RequestRecv, duplex: Duplex) -> Self {
        Self {
            cancel,
            request_recv,
            response_sends: ResponseSends::new(),
            duplex,
        }
    }

    pub(crate) async fn run(mut self) -> Result<(), io::Error> {
        let mut deadline = None;
        tokio::pin! { let timeout = OptionFuture::from(None); }

        loop {
            let next_deadline = self.response_sends.next_deadline();
            if deadline != next_deadline {
                deadline = next_deadline;
                timeout.set(deadline.map(time::sleep_until).into());
            }

            tokio::select! {
                () = self.cancel.wait() => break,

                request = self.request_recv.recv() => {
                    let Some(request) = request else { break };
                    // Block the actor loop on `duplex.send` because it is probably desirable to
                    // derive back pressure from this point.
                    self.handle_request(request).await?;
                }

                response = self.duplex.try_next() => {
                    let Some(response) = response? else { break };
                    self.handle_response(response)?;
                }

                Some(()) = &mut timeout => {
                    self.response_sends.remove_expired(Instant::now());
                    deadline = None;
                    timeout.set(None.into());
                }
            }
        }

        Ok(())
    }

    async fn handle_request(&mut self, (request, response_send): Request) -> Result<(), io::Error> {
        tracing::debug!(?request);
        let routing_id = self.response_sends.insert(response_send);
        let request = Envelope::new(
            vec![Frame::from(routing_id.to_be_bytes().as_slice())],
            Frame::from(Vec::<u8>::from(request)),
        );
        self.duplex.send(request.into()).await
    }

    fn handle_response(&mut self, frames: Multipart) -> Result<(), io::Error> {
        let response = envelope::decode(frames).context(InvalidResponseSnafu)?;

        let routing_id = response.routing_id();
        ensure!(
            routing_id.len() == 1 && routing_id[0].len() == 8,
            InvalidRoutingIdSnafu { response },
        );
        let routing_id = RoutingId::from_be_bytes((*routing_id[0]).try_into().unwrap());

        let response = self.decode(response);
        tracing::debug!(?response);

        let Some(response_send) = self.response_sends.remove(routing_id) else {
            tracing::debug!(routing_id, "response_send not found");
            return Ok(());
        };

        let _ = response_send.send(response);
        Ok(())
    }

    fn decode(&self, response: Envelope<Frame>) -> ResponseResult {
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
