use std::io::Error;
use std::sync::{Arc, Mutex};

use tokio::sync::mpsc::{self, UnboundedSender};

use g1_base::sync::MutexExt;
use g1_tokio::{
    bstream::{StreamRecv, StreamSend},
    task::{Cancel, JoinGuard},
};

use bittorrent_base::{BlockDesc, Features, PeerId};
use bittorrent_extension::{Enabled, ExtensionIdMap};
use bittorrent_socket::{Message, Socket};

use crate::{
    actor::Actor,
    chan::{Endpoint, ExtensionMessageOwner, Sends},
    incoming,
    outgoing::{self, ResponseRecv},
    state::{self, ConnStateUpper},
    Full, Incompatible, Possession,
};

#[derive(Clone, Debug)]
pub struct Peer(Arc<PeerInner>);

#[derive(Debug)]
struct PeerInner {
    cancel: Cancel,

    self_features: Features,

    peer_id: PeerId,
    peer_endpoint: Endpoint,
    peer_features: Features,

    extension_ids: Arc<Mutex<ExtensionIdMap>>,

    conn_state: ConnStateUpper,
    outgoings: outgoing::QueueUpper,
    message_send: UnboundedSender<Message>,
}

pub type PeerGuard = JoinGuard<Result<(), Error>>;

macro_rules! ensure_feature {
    ($self:ident, $feature:ident $(,)?) => {
        if !$self.0.self_features.$feature || !$self.0.peer_features.$feature {
            return Err(Incompatible);
        }
    };
}

impl Peer {
    pub fn spawn<Stream>(
        socket: Socket<Stream>,
        peer_endpoint: Endpoint,
        sends: Sends,
    ) -> (Self, PeerGuard)
    where
        Stream: StreamRecv<Error = Error> + StreamSend<Error = Error> + Send + 'static,
    {
        let self_features = socket.self_features();
        let peer_id = socket.peer_id();
        let peer_features = socket.peer_features();
        let extension_ids = Arc::new(Mutex::new(ExtensionIdMap::new()));
        let (conn_state_upper, conn_state_lower) = state::new_conn_state();
        let (outgoings_upper, outgoings_lower) = outgoing::new_queue(
            u64::try_from(*bittorrent_base::recv_buffer_capacity()).unwrap(),
            *crate::request_timeout(),
        );
        let (message_send, message_recv) = mpsc::unbounded_channel();
        let guard = {
            let extension_ids = extension_ids.clone();
            JoinGuard::spawn(move |cancel| {
                let incomings = incoming::Queue::new(
                    u64::try_from(*bittorrent_base::send_buffer_capacity()).unwrap(),
                    cancel.clone(),
                );
                Actor::new(
                    cancel,
                    socket,
                    extension_ids,
                    conn_state_lower,
                    incomings,
                    outgoings_lower,
                    message_recv,
                    peer_endpoint,
                    sends,
                )
                .run()
            })
        };
        (
            Self(Arc::new(PeerInner {
                cancel: guard.cancel_handle(),
                self_features,
                peer_id,
                peer_endpoint,
                peer_features,
                extension_ids,
                conn_state: conn_state_upper,
                outgoings: outgoings_upper,
                message_send,
            })),
            guard,
        )
    }

    pub fn peer_id(&self) -> PeerId {
        self.0.peer_id.clone()
    }

    pub fn peer_endpoint(&self) -> Endpoint {
        self.0.peer_endpoint
    }

    pub fn peer_features(&self) -> Features {
        self.0.peer_features
    }

    pub fn peer_extensions(&self) -> Enabled {
        self.0.extension_ids.must_lock().peer_extensions()
    }

    pub fn cancel(&self) {
        self.0.cancel.set();
    }

    fn send_message(&self, message: Message) {
        if self.0.message_send.send(message).is_err() {
            tracing::warn!("peer actor was shut down");
        }
    }

    //
    // Connection State
    //

    pub fn self_choking(&self) -> bool {
        self.0.conn_state.self_choking.get()
    }

    pub fn set_self_choking(&self, value: bool) {
        self.0.conn_state.self_choking.set(value)
    }

    pub fn self_interested(&self) -> bool {
        self.0.conn_state.self_interested.get()
    }

    pub fn set_self_interested(&self, value: bool) {
        self.0.conn_state.self_interested.set(value);
    }

    pub fn peer_choking(&self) -> bool {
        self.0.conn_state.peer_choking.get()
    }

    pub fn peer_interested(&self) -> bool {
        self.0.conn_state.peer_interested.get()
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
    // TODO: At the moment, `Peer` is not sending `Suggest` or `AllowedFast` to the peer.
    //

    pub fn request(&self, desc: BlockDesc) -> Result<Option<ResponseRecv>, Full> {
        self.0.outgoings.enqueue(desc)
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

    pub fn send_extension(&self, message_owner: ExtensionMessageOwner) -> Result<(), Incompatible> {
        ensure_feature!(self, extension);
        let id = {
            let message = message_owner.deref();
            if !message.is_enabled() {
                return Err(Incompatible);
            }
            self.0
                .extension_ids
                .must_lock()
                .map(message)
                .ok_or(Incompatible)?
        };
        let payload = ExtensionMessageOwner::into_buffer(message_owner);
        self.send_message(Message::Extended(id, payload));
        Ok(())
    }
}
