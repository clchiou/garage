//! Channels to which peer agents send data.

use std::net::SocketAddr;

use bytes::Bytes;
use tokio::sync::mpsc::{self, Receiver, Sender};

use bittorrent_base::{BlockDesc, PieceIndex};

use crate::{incoming::ResponseSend, Possession};

// NOTE: For now, we use the peer endpoint to uniquely identify a peer, regardless of the transport
// layer protocol (TCP vs uTP) used by the peer.
pub type Endpoint = SocketAddr;

#[derive(Debug)]
pub struct Recvs {
    pub interested_recv: Receiver<Endpoint>,
    pub request_recv: Receiver<(Endpoint, BlockDesc, ResponseSend)>,

    pub possession_recv: Receiver<(Endpoint, Possession)>,
    pub suggest_recv: Receiver<(Endpoint, PieceIndex)>,
    pub allowed_fast_recv: Receiver<(Endpoint, PieceIndex)>,
    /// Channel of blocks we receive despite not having requested them.
    pub block_recv: Receiver<(Endpoint, (BlockDesc, Bytes))>,

    pub port_recv: Receiver<(Endpoint, u16)>,

    pub extension_recv: Receiver<(Endpoint, (u8, Bytes))>,
}

#[derive(Clone, Debug)]
pub struct Sends {
    pub(crate) interested_send: Sender<Endpoint>,
    pub(crate) request_send: Sender<(Endpoint, BlockDesc, ResponseSend)>,

    pub(crate) possession_send: Sender<(Endpoint, Possession)>,
    pub(crate) suggest_send: Sender<(Endpoint, PieceIndex)>,
    pub(crate) allowed_fast_send: Sender<(Endpoint, PieceIndex)>,
    pub(crate) block_send: Sender<(Endpoint, (BlockDesc, Bytes))>,

    pub(crate) port_send: Sender<(Endpoint, u16)>,

    pub(crate) extension_send: Sender<(Endpoint, (u8, Bytes))>,
}

pub fn new_channels() -> (Recvs, Sends) {
    let (interested_send, interested_recv) = mpsc::channel(*crate::interested_queue_size());
    let (request_send, request_recv) = mpsc::channel(*crate::request_queue_size());

    let (possession_send, possession_recv) = mpsc::channel(*crate::possession_queue_size());
    let (suggest_send, suggest_recv) = mpsc::channel(*crate::suggest_queue_size());
    let (allowed_fast_send, allowed_fast_recv) = mpsc::channel(*crate::allowed_fast_queue_size());
    let (block_send, block_recv) = mpsc::channel(*crate::block_queue_size());

    let (port_send, port_recv) = mpsc::channel(*crate::port_queue_size());

    let (extension_send, extension_recv) = mpsc::channel(*crate::extension_queue_size());

    (
        Recvs {
            interested_recv,
            request_recv,

            possession_recv,
            suggest_recv,
            allowed_fast_recv,
            block_recv,

            port_recv,

            extension_recv,
        },
        Sends {
            interested_send,
            request_send,

            possession_send,
            suggest_send,
            allowed_fast_send,
            block_send,

            port_send,

            extension_send,
        },
    )
}
