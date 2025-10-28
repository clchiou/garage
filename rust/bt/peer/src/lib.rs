#![feature(assert_matches)]

// It appears that the BitTorrent community does not have a term for the connections of an
// uninitialized torrent.  For the time being, we will refer to them as "half-open".
//
// TODO: There is significant duplication between the half-open and normal connection codes. Can
// they be shared?
pub mod half_open;

mod broadcast;
mod conn;
mod error;
mod manifold;
mod model;

use std::io;
use std::sync::Arc;

use futures::sink::SinkExt;

use g1_base::fmt::DebugExt;
use g1_tokio::sync::broadcast::Receiver;

use bt_base::{ConnId, Features};
use bt_proto::{BoxSink, BoxStream, Message};

use crate::broadcast::Broadcast;
use crate::half_open::Backlog;

pub use crate::conn::Conn;
pub use crate::error::Error;
pub use crate::manifold::{Manifold, ManifoldGuard};

#[derive(DebugExt)]
pub struct ConnArgs {
    pub conn_id: ConnId,

    pub self_features: Features,
    pub peer_features: Features,

    #[debug(skip)]
    pub stream: BoxStream,
    #[debug(skip)]
    pub sink: BoxSink,
}

#[derive(Clone, Debug)]
pub enum PeerMessage {
    Connect(ConnId),
    Message(ConnId, Message),
    // It is unusual to wrap errors in an `Arc`, but the broadcast channel requires the message
    // type to implement `Clone`.
    Disconnect(ConnId, Result<(), Arc<io::Error>>),
}

pub type PeerMessageRecv = Receiver<PeerMessage>;
type PeerMessageSend = Broadcast<PeerMessage>;

impl ConnArgs {
    async fn convert_connect_result(result: Result<bool, Option<(ConnArgs,)>>) -> bool {
        match result {
            Ok(spawned) => spawned,
            Err(args) => {
                if let Some((args,)) = args {
                    let ConnArgs {
                        conn_id, mut sink, ..
                    } = args;
                    if let Err(error) = sink.close().await {
                        tracing::warn!(%conn_id, %error, "manifold exit; close conn");
                    }
                }
                false
            }
        }
    }

    async fn convert_with_backlog_result(
        result: Result<bool, Option<(ConnArgs, Backlog)>>,
    ) -> bool {
        Self::convert_connect_result(result.map_err(|pair| pair.map(|(args, _)| (args,)))).await
    }
}

impl PeerMessage {
    pub fn conn_id(&self) -> &ConnId {
        match self {
            Self::Connect(conn_id) => conn_id,
            Self::Message(conn_id, _) => conn_id,
            Self::Disconnect(conn_id, _) => conn_id,
        }
    }
}
