use std::io::{Error, ErrorKind};
use std::sync::Arc;

use bytes::Bytes;
use tokio::{
    sync::{
        mpsc::{self, UnboundedSender},
        Mutex, Notify,
    },
    task::JoinHandle,
};
use tracing::Instrument;

use g1_tokio::{
    bstream::{StreamRecv, StreamSend},
    task::{self, JoinTaskError},
};

use bittorrent_base::{BlockDesc, Features, PeerId};
use bittorrent_socket::{Message, Socket};

use crate::{
    actor::Actor,
    chan::{Endpoint, Sends},
    error, incoming,
    outgoing::{self, ResponseRecv},
    state::{self, ConnStateUpper},
    Full, Incompatible, Possession,
};

#[derive(Debug)]
pub struct Agent {
    self_features: Features,

    peer_id: PeerId,
    peer_endpoint: Endpoint,
    peer_features: Features,

    conn_state: ConnStateUpper,
    outgoings: outgoing::QueueUpper,
    message_send: UnboundedSender<Message>,

    exit: Arc<Notify>,
    task: Mutex<JoinHandle<Result<(), Error>>>,
}

macro_rules! ensure_feature {
    ($self:ident, $feature:ident $(,)?) => {
        if !$self.self_features.$feature || !$self.peer_features.$feature {
            return Err(Incompatible);
        }
    };
}

impl Agent {
    pub fn new<Stream>(socket: Socket<Stream>, peer_endpoint: Endpoint, sends: Sends) -> Self
    where
        Stream: StreamRecv<Error = Error> + StreamSend<Error = Error> + Send + 'static,
    {
        let self_features = socket.self_features();
        let peer_id = socket.peer_id();
        let peer_features = socket.peer_features();
        let (conn_state_upper, conn_state_lower) = state::new_conn_state();
        let incomings =
            incoming::Queue::new(u64::try_from(*bittorrent_base::send_buffer_capacity()).unwrap());
        let (outgoings_upper, outgoings_lower) = outgoing::new_queue(
            u64::try_from(*bittorrent_base::recv_buffer_capacity()).unwrap(),
            *crate::request_timeout(),
        );
        let (message_send, message_recv) = mpsc::unbounded_channel();
        let exit = Arc::new(Notify::new());

        let actor = Actor::new(
            exit.clone(),
            socket,
            conn_state_lower,
            incomings,
            outgoings_lower,
            message_recv,
            peer_endpoint,
            sends,
        );
        let actor_run = actor
            .run()
            .instrument(tracing::info_span!("peer", ?peer_endpoint));

        Self {
            self_features,
            peer_id,
            peer_endpoint,
            peer_features,
            conn_state: conn_state_upper,
            outgoings: outgoings_upper,
            message_send,
            exit,
            task: Mutex::new(tokio::spawn(actor_run)),
        }
    }

    pub fn peer_id(&self) -> PeerId {
        self.peer_id.clone()
    }

    pub fn peer_endpoint(&self) -> Endpoint {
        self.peer_endpoint
    }

    pub fn peer_features(&self) -> Features {
        self.peer_features
    }

    pub async fn join(&self) {
        self.message_send.closed().await;
    }

    pub fn close(&self) {
        self.exit.notify_one();
    }

    pub async fn shutdown(&self) -> Result<(), Error> {
        self.close();
        task::join_task(&self.task, *crate::grace_period())
            .await
            .map_err(|error| match error {
                JoinTaskError::Cancelled => Error::other(error::Error::Cancelled),
                JoinTaskError::Timeout => Error::new(
                    ErrorKind::TimedOut,
                    error::Error::ShutdownGracePeriodExceeded,
                ),
            })?
    }

    fn send_message(&self, message: Message) {
        if self.message_send.send(message).is_err() {
            tracing::warn!("peer actor was shut down");
        }
    }

    //
    // Connection State
    //

    pub fn self_choking(&self) -> bool {
        self.conn_state.self_choking.get()
    }

    pub fn set_self_choking(&self, value: bool) {
        self.conn_state.self_choking.set(value)
    }

    pub fn self_interested(&self) -> bool {
        self.conn_state.self_interested.get()
    }

    pub fn set_self_interested(&self, value: bool) {
        self.conn_state.self_interested.set(value);
    }

    pub fn peer_choking(&self) -> bool {
        self.conn_state.peer_choking.get()
    }

    pub fn peer_interested(&self) -> bool {
        self.conn_state.peer_interested.get()
    }

    //
    // Piece Possession
    //

    pub fn possess(&self, possession: Possession) -> Result<(), Incompatible> {
        match possession {
            Possession::Bitfield(bitfield) => self.send_message(Message::Bitfield(bitfield)),
            Possession::Have(index) => self.send_message(Message::Have(index)),
            Possession::HaveAll => {
                ensure_feature!(self, fast);
                self.send_message(Message::HaveAll);
            }
            Possession::HaveNone => {
                ensure_feature!(self, fast);
                self.send_message(Message::HaveNone);
            }
        }
        Ok(())
    }

    //
    // Piece Exchange
    //
    // TODO: At the moment, `Agent` is not sending `Suggest` or `AllowedFast` to the peer.
    //

    pub fn request(&self, desc: BlockDesc) -> Result<Option<ResponseRecv>, Full> {
        self.outgoings.enqueue(desc)
    }

    //
    // DHT
    //

    pub fn send_port(&self, port: u16) -> Result<(), Incompatible> {
        ensure_feature!(self, dht);
        self.send_message(Message::Port(port));
        Ok(())
    }

    //
    // Extension
    //

    pub fn send_extension(&self, id: u8, payload: Bytes) -> Result<(), Incompatible> {
        ensure_feature!(self, extension);
        self.send_message(Message::Extended(id, payload));
        Ok(())
    }
}

impl Drop for Agent {
    fn drop(&mut self) {
        self.task.get_mut().abort();
    }
}
