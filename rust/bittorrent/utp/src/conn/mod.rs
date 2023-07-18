mod actor;
mod handshake;
mod rtt;
mod state;
mod window;

use std::io;
use std::net::SocketAddr;

use bytes::Bytes;
use snafu::prelude::*;
use tokio::sync::mpsc::{self, Receiver, Sender};

use crate::packet::{self, Packet};
use crate::timestamp::Timestamp;

pub(crate) use self::actor::Actor;
pub(crate) use self::handshake::Handshake;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub(crate) enum Error {
    BrokenPipe,
    UnexpectedEof,

    RecvBufferTimeout,

    #[snafu(display("resend limit exceeded: seq={seq}"))]
    ResendLimitExceeded {
        seq: u16,
    },

    InvalidPacket {
        source: packet::Error,
    },

    #[snafu(display("ack exceed seq: ack={ack} seq={seq}"))]
    AckExceedSeq {
        ack: u16,
        seq: u16,
    },
    #[snafu(display("different eof seq: old={old} new={new}"))]
    DifferentEof {
        old: u16,
        new: u16,
    },
    #[snafu(display("distant seq: seq={seq} in_order_seq={in_order_seq}"))]
    DistantSeq {
        seq: u16,
        in_order_seq: u16,
    },
    #[snafu(display("seq exceed eof seq: seq={seq} eof={eof}"))]
    SeqExceedEof {
        seq: u16,
        eof: u16,
    },
}

g1_param::define!(incoming_queue_size: usize = 32);
g1_param::define!(outgoing_queue_size: usize = 256);

pub(crate) type Incoming = (Bytes, Timestamp);
pub(crate) type IncomingRecv = Receiver<Incoming>;
pub(crate) type IncomingSend = Sender<Incoming>;

pub(crate) type Outgoing = (SocketAddr, Packet);
pub(crate) type OutgoingRecv = Receiver<Outgoing>;
pub(crate) type OutgoingSend = Sender<Outgoing>;

pub(crate) fn new_outgoing_queue() -> (OutgoingRecv, OutgoingSend) {
    let (send, recv) = mpsc::channel(*outgoing_queue_size());
    (recv, send)
}

impl Error {
    fn to_io_error(&self) -> io::Error {
        match self {
            Error::BrokenPipe => {
                io::Error::new(io::ErrorKind::BrokenPipe, "utp socket is shutting down")
            }
            Error::UnexpectedEof => {
                io::Error::new(io::ErrorKind::UnexpectedEof, "utp connection is closing")
            }

            Error::RecvBufferTimeout => {
                io::Error::new(io::ErrorKind::TimedOut, "utp recv buffer timeout")
            }

            Error::ResendLimitExceeded { .. } => {
                io::Error::new(io::ErrorKind::TimedOut, self.clone())
            }

            Error::InvalidPacket { source } => {
                io::Error::new(io::ErrorKind::ConnectionAborted, source.clone())
            }

            Error::AckExceedSeq { .. }
            | Error::DifferentEof { .. }
            | Error::DistantSeq { .. }
            | Error::SeqExceedEof { .. } => {
                io::Error::new(io::ErrorKind::ConnectionAborted, self.clone())
            }
        }
    }
}

const MIN_PACKET_SIZE: usize = 150;
