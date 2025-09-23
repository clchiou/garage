mod conn;
mod manifold;

use std::io;
use std::sync::Arc;

use bytes::Bytes;

use g1_tokio::sync::broadcast::Receiver;

use bt_base::ConnId;
use bt_proto::Message;

use crate::broadcast::Broadcast;

pub use self::conn::HalfOpenConn;
pub use self::manifold::{HalfOpenManifold, HalfOpenManifoldGuard};

#[derive(Clone, Debug)]
pub enum HalfOpenMessage {
    Connect(ConnId),
    // Only `bt_proto::Message::Extended` may be exchanged over a half-open connection.
    Extended(ConnId, u8, Bytes),
    // It is unusual to wrap errors in an `Arc`, but the broadcast channel requires the message
    // type to implement `Clone`.
    Disconnect(ConnId, Result<(), Arc<io::Error>>),
}

pub type HalfOpenMessageRecv = Receiver<HalfOpenMessage>;
type HalfOpenMessageSend = Broadcast<HalfOpenMessage>;

pub(crate) type Backlog = Vec<Message>;

impl HalfOpenMessage {
    pub fn conn_id(&self) -> &ConnId {
        match self {
            Self::Connect(conn_id) => conn_id,
            Self::Extended(conn_id, _, _) => conn_id,
            Self::Disconnect(conn_id, _) => conn_id,
        }
    }
}
