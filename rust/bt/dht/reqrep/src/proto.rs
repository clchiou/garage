use std::future;
use std::io::Error;
use std::net::SocketAddr;

use futures::sink::SinkExt;
use futures::stream::StreamExt;

use g1_msg::reqrep::{self, Protocol};

use bt_dht_proto::{Message, Txid};
use bt_udp::{Sink, Stream};

#[derive(Clone, Copy, Debug)]
pub struct MessageProtocol;

pub(crate) type ReqRepInner = reqrep::ReqRep<MessageProtocol>;
pub type ReqRepGuard = reqrep::Guard<MessageProtocol>;

pub(crate) type ResponseSend = reqrep::ResponseSend<MessageProtocol>;

impl Protocol for MessageProtocol {
    type Id = (SocketAddr, Txid);
    type Incoming = (SocketAddr, Message);
    type Outgoing = (SocketAddr, Message);

    type Error = Error;

    fn incoming_id((node_endpoint, message): &Self::Incoming) -> Self::Id {
        (*node_endpoint, message.txid.clone())
    }

    fn outgoing_id((node_endpoint, message): &Self::Outgoing) -> Self::Id {
        (*node_endpoint, message.txid.clone())
    }
}

pub(crate) type MessageStream<I: Stream> = impl reqrep::Stream<MessageProtocol>;
pub(crate) type MessageSink<O: Sink> = impl reqrep::Sink<MessageProtocol>;

#[define_opaque(MessageStream)]
pub(crate) fn decode<I>(stream: I) -> MessageStream<I>
where
    I: Stream,
{
    stream.filter_map(|item| {
        future::ready(match item {
            Ok((endpoint, payload)) => {
                let mut buffer = &*payload;
                match bt_bencode::from_buf(&mut buffer) {
                    Ok(message) => {
                        if !buffer.is_empty() {
                            tracing::warn!(
                                %endpoint,
                                ?message,
                                trailing_data = %buffer.escape_ascii(),
                                "incoming",
                            );
                        }
                        Some(Ok((endpoint, message)))
                    }
                    Err(error) => {
                        tracing::warn!(%error, %endpoint, ?payload, "incoming");
                        None
                    }
                }
            }
            Err(error) => Some(Err(error)),
        })
    })
}

#[define_opaque(MessageSink)]
pub(crate) fn encode<O>(sink: O) -> MessageSink<O>
where
    O: Sink,
{
    sink.with(|(endpoint, message)| {
        future::ready(Ok((
            endpoint,
            bt_bencode::to_bytes(&message).expect("to_bytes should never fail"),
        )))
    })
}
