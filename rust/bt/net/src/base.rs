use std::collections::HashMap;
use std::collections::hash_map::Entry;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use futures::sink::SinkExt;
use tokio::io::{AsyncRead, AsyncWrite};
use tokio::net::TcpStream;

use g1_base::sync::MutexExt;
use g1_tokio::task::{JoinGuard, JoinQueue};

use bt_base::{ConnId, Features, InfoHash, PeerEndpoint, PeerId};
use bt_model::Model;
use bt_peer::half_open::HalfOpenManifold;
use bt_peer::{ConnArgs, Manifold};
use bt_proto::{BoxSink, BoxStream, tcp};

pub(crate) struct Shared {
    self_features: Features,

    pub(crate) model: Arc<Mutex<Model>>,

    pub(crate) self_endpoints: Mutex<Vec<PeerEndpoint>>,

    // We track connectable connections for two reasons:
    // * To avoid creating redundant connections.  Each `(info_hash, peer_endpoint)` pair should
    //   have at most one connection.
    // * To reconnect them.
    //
    // TODO: I think most of this crate's complexity comes from synchronizing `conn_table` with
    // `bt_model` and `bt_peer`, and this synchronization feels somewhat fragile.  Is there a
    // better approach?
    pub(crate) conn_table: Mutex<ConnTable>,

    pub(crate) handshaker: Handshaker,
    pub(crate) handshake_tasks: JoinQueue<()>,

    manifold: Manifold,
    half_open: Option<HalfOpenManifold>,
}

pub(crate) struct ConnTable(HashMap<(InfoHash, PeerEndpoint), ConnState>);

#[derive(Debug)]
struct ConnState {
    self_endpoint: Option<PeerEndpoint>,
    // TODO: If `proto` is set, we should try this protocol first when reconnecting.
    proto: Option<Proto>,
    num_reconns: u32,
}

#[derive(Debug)]
pub(crate) enum Proto {
    Tcp,
    // TODO: uTP.
}

pub(crate) type Handshaker = bt_proto::Handshaker<MatchInfoHash>;

pub(crate) type MatchInfoHash = impl Fn(InfoHash) -> bool + Clone;

#[define_opaque(MatchInfoHash)]
fn make_match_info_hash(model: Arc<Mutex<Model>>) -> MatchInfoHash {
    // Check `peers().contain_torrent()` instead of `torrents().contains()` because the torrents
    // might not have been initialized yet.
    move |info_hash| model.must_lock().peers().contains_torrent(info_hash)
}

pub(crate) type HandshakeGuard = JoinGuard<()>;

pub(crate) enum RawConn {
    Tcp(TcpStream),
    // TODO: uTP.
}

pub(crate) trait AsyncReadWrite: AsyncRead + AsyncWrite {}

impl<T> AsyncReadWrite for T where T: AsyncRead + AsyncWrite {}

// TODO: Make these configurable.
const RECONNECT_LIMIT: u32 = 3;
const RECONNECT_BACKOFF_BASE: Duration = Duration::from_secs(1);

impl Shared {
    pub(crate) fn new(
        self_id: PeerId,
        self_features: Features,
        model: Arc<Mutex<Model>>,
        manifold: Manifold,
        half_open: Option<HalfOpenManifold>,
    ) -> Self {
        let match_info_hash = make_match_info_hash(model.clone());
        Self {
            self_features,
            model,
            self_endpoints: Mutex::new(Vec::new()),
            conn_table: Mutex::new(ConnTable::new()),
            handshaker: Handshaker::new(self_id, self_features, match_info_hash),
            handshake_tasks: JoinQueue::new(),
            manifold,
            half_open,
        }
    }

    pub(crate) async fn spawn(
        &self,
        conn_id: ConnId,
        peer_features: Features,
        raw_conn: RawConn,
        remove_if_not_spawn: bool,
    ) {
        let (stream, sink) = raw_conn.into_framed();
        let mut args = ConnArgs {
            conn_id: conn_id.clone(),
            self_features: self.self_features,
            peer_features,
            stream,
            sink,
        };

        let result = if self
            .model
            .must_lock()
            .torrents()
            .contains(conn_id.info_hash())
        {
            Ok(self.manifold.connect(args).await)
        } else if let Some(half_open) = self.half_open.as_ref() {
            Ok(half_open.connect(args).await)
        } else {
            args.sink.close().await.map(|()| false)
        };
        match &result {
            Ok(true) => {}
            Ok(false) => tracing::warn!(%conn_id, "conn not spawn"),
            Err(error) => tracing::warn!(%conn_id, %error, "conn not spawn; close"),
        }

        if remove_if_not_spawn && matches!(result, Ok(false) | Err(_)) {
            self.conn_table.must_lock().remove_connected(conn_id);
        }
    }
}

impl ConnTable {
    fn new() -> Self {
        Self(HashMap::new())
    }

    //
    // Connecting
    //

    pub(crate) fn connecting(&mut self, info_hash: InfoHash, peer_endpoint: PeerEndpoint) -> bool {
        match self.0.entry((info_hash, peer_endpoint)) {
            Entry::Occupied(_) => false,
            Entry::Vacant(entry) => {
                entry.insert(ConnState::connecting());
                true
            }
        }
    }

    // NOTE: The caller must ensure that this entry is present and `!is_connected()`.
    pub(crate) fn reconnect_backoff(
        &self,
        info_hash: InfoHash,
        peer_endpoint: PeerEndpoint,
    ) -> Option<Duration> {
        let state = self.0.get(&(info_hash, peer_endpoint)).expect("connecting");
        assert!(!state.is_connected(), "state = {state:?}");
        state.backoff()
    }

    // NOTE: The caller must ensure that this entry is present and `!is_connected()`.
    pub(crate) fn connecting_connected(&mut self, conn_id: ConnId, proto: Proto) {
        let ConnId {
            info_hash,
            conn_pair: (self_endpoint, peer_endpoint),
        } = conn_id;
        let state = self
            .0
            .get_mut(&(info_hash, peer_endpoint))
            .expect("expect connecting");
        assert!(!state.is_connected(), "state = {state:?}");
        state.self_endpoint = Some(self_endpoint);
        state.proto = Some(proto);
    }

    // NOTE: The caller must ensure that this entry is present and `!is_connected()`.
    pub(crate) fn connecting_disconnected(
        &mut self,
        info_hash: InfoHash,
        peer_endpoint: PeerEndpoint,
    ) -> bool {
        // TODO: Refactor this with `Self::disconnected()`.

        let Entry::Occupied(mut entry) = self.0.entry((info_hash.clone(), peer_endpoint)) else {
            panic!("expect connecting: {info_hash}, {peer_endpoint}");
        };

        let state = entry.get_mut();
        assert!(!state.is_connected(), "state = {state:?}");

        let reconnect = state.num_reconns < RECONNECT_LIMIT;
        if reconnect {
            state.num_reconns += 1;
        } else {
            entry.remove();
        }
        reconnect
    }

    // NOTE: The caller must ensure that this entry is present and is `!is_connected()`.
    pub(crate) fn remove_connecting(&mut self, info_hash: InfoHash, peer_endpoint: PeerEndpoint) {
        match self.0.entry((info_hash, peer_endpoint)) {
            Entry::Occupied(entry) => {
                let state = entry.get();
                assert!(!state.is_connected(), "state = {state:?}");
                entry.remove();
            }
            Entry::Vacant(entry) => {
                let (info_hash, peer_endpoint) = entry.key();
                panic!("expect connecting: {info_hash}, {peer_endpoint}");
            }
        }
    }

    //
    // Connected
    //

    pub(crate) fn connected(&mut self, conn_id: ConnId, proto: Proto) -> bool {
        let ConnId {
            info_hash,
            conn_pair: (self_endpoint, peer_endpoint),
        } = conn_id;
        match self.0.entry((info_hash, peer_endpoint)) {
            Entry::Occupied(_) => false,
            Entry::Vacant(entry) => {
                entry.insert(ConnState::connected(self_endpoint, proto));
                true
            }
        }
    }

    pub(crate) fn assert_connected(&self, conn_id: &ConnId) {
        let ConnId {
            info_hash,
            conn_pair: (self_endpoint, peer_endpoint),
        } = conn_id.clone();
        if let Some(state) = self
            .0
            .get(&(info_hash, peer_endpoint))
            .filter(|state| state.self_endpoint == Some(self_endpoint))
        {
            assert!(state.is_connected(), "state = {state:?}");
        }
    }

    pub(crate) fn disconnected(&mut self, conn_id: ConnId) -> Option<bool> {
        let ConnId {
            info_hash,
            conn_pair: (self_endpoint, peer_endpoint),
        } = conn_id;
        let Entry::Occupied(mut entry) = self.0.entry((info_hash, peer_endpoint)) else {
            return None;
        };

        let state = entry.get_mut();
        if state.self_endpoint != Some(self_endpoint) {
            return None;
        }

        let reconnect = state.num_reconns < RECONNECT_LIMIT;
        if reconnect {
            state.self_endpoint = None;
            state.num_reconns += 1;
        } else {
            entry.remove();
        }
        Some(reconnect)
    }

    fn remove_connected(&mut self, conn_id: ConnId) {
        let ConnId {
            info_hash,
            conn_pair: (self_endpoint, peer_endpoint),
        } = conn_id;
        let Entry::Occupied(entry) = self.0.entry((info_hash, peer_endpoint)) else {
            return;
        };

        let state = entry.get();
        if state.self_endpoint != Some(self_endpoint) {
            return;
        }

        entry.remove();
    }
}

impl ConnState {
    fn connecting() -> Self {
        Self {
            self_endpoint: None,
            proto: None,
            num_reconns: 0,
        }
    }

    fn connected(self_endpoint: PeerEndpoint, proto: Proto) -> Self {
        Self {
            self_endpoint: Some(self_endpoint),
            proto: Some(proto),
            num_reconns: 0,
        }
    }

    fn is_connected(&self) -> bool {
        self.self_endpoint.is_some()
    }

    fn backoff(&self) -> Option<Duration> {
        (self.num_reconns > 0).then(|| {
            RECONNECT_BACKOFF_BASE.saturating_mul(2u32.saturating_pow(self.num_reconns - 1))
        })
    }
}

impl RawConn {
    pub(crate) fn proto(&self) -> Proto {
        match self {
            Self::Tcp(_) => Proto::Tcp,
        }
    }

    // This is simpler than implementing `AsyncRead` and `AsyncWrite` for `RawConn`.
    pub(crate) fn raw_conn(&mut self) -> &mut (dyn AsyncReadWrite + Send + Unpin) {
        match self {
            Self::Tcp(raw_conn) => raw_conn,
        }
    }

    pub(crate) fn into_framed(self) -> (BoxStream, BoxSink) {
        match self {
            Self::Tcp(raw_conn) => {
                let (stream, sink) = tcp::into_split(raw_conn);
                (Box::new(stream), Box::new(sink))
            }
        }
    }
}
