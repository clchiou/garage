mod actor;
mod control;
mod handshake;
mod recv;
mod rtt;
mod send;
mod state;
mod window;

use std::io;
use std::net::SocketAddr;

use bytes::Bytes;
use snafu::prelude::*;
use tokio::sync::{
    mpsc::{self, Receiver, Sender},
    oneshot,
};

use crate::packet::{self, Packet, PacketType};
use crate::timestamp::Timestamp;

pub(crate) use self::actor::Actor;
pub(crate) use self::handshake::Handshake;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub(crate) enum Error {
    BrokenPipe,
    UnexpectedEof,

    ConnectTimeout,
    AcceptTimeout,

    ConnectionReset,

    RecvBufferTimeout,
    RecvGracePeriodExpired,

    SendTimeout,

    #[snafu(display("resend limit exceeded: seq={seq}"))]
    ResendLimitExceeded {
        seq: u16,
    },

    InvalidPacket {
        source: packet::Error,
    },

    #[snafu(display("expect packet type {expect:?}: {packet_type:?}"))]
    ExpectPacketType {
        packet_type: PacketType,
        expect: PacketType,
    },
    UnexpectedResynchronize,

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

pub(crate) type Connected = Result<(), io::Error>;
pub(crate) type ConnectedRecv = oneshot::Receiver<Connected>;
pub(crate) type ConnectedSend = oneshot::Sender<Connected>;

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

            Error::ConnectTimeout => io::Error::new(io::ErrorKind::TimedOut, "utp connect timeout"),
            Error::AcceptTimeout => io::Error::new(io::ErrorKind::TimedOut, "utp accept timeout"),

            Error::ConnectionReset => io::Error::new(
                io::ErrorKind::ConnectionReset,
                "utp connection is reset by peer",
            ),

            Error::RecvBufferTimeout => {
                io::Error::new(io::ErrorKind::TimedOut, "utp recv buffer timeout")
            }
            Error::RecvGracePeriodExpired => {
                io::Error::new(io::ErrorKind::TimedOut, "utp recv grace period expired")
            }

            Error::SendTimeout => io::Error::new(io::ErrorKind::TimedOut, "utp send timeout"),

            Error::ResendLimitExceeded { .. } => {
                io::Error::new(io::ErrorKind::TimedOut, self.clone())
            }

            Error::InvalidPacket { source } => {
                io::Error::new(io::ErrorKind::ConnectionAborted, source.clone())
            }

            Error::ExpectPacketType { .. }
            | Error::UnexpectedResynchronize
            | Error::AckExceedSeq { .. }
            | Error::DifferentEof { .. }
            | Error::DistantSeq { .. }
            | Error::SeqExceedEof { .. } => {
                io::Error::new(io::ErrorKind::ConnectionAborted, self.clone())
            }
        }
    }
}

const MIN_PACKET_SIZE: usize = 150;
