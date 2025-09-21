use std::sync::atomic::{AtomicBool, Ordering};

use bt_base::{ConnId, Features};

use crate::{ModelUpdate, ModelUpdateSend};

#[derive(Debug)]
pub struct ConnState {
    conn_id: ConnId,

    peer_features: Features,

    self_choking: AtomicBool,
    peer_choking: AtomicBool,

    self_interested: AtomicBool,
    peer_interested: AtomicBool,

    // Snubbing is not defined in the BEPs, but it is commonly implemented by BitTorrent clients.
    // When we snub a peer, we effectively choke it and stop sending requests to it.
    snubbing: AtomicBool,

    model_update_send: ModelUpdateSend,
}

impl ConnState {
    pub(crate) fn new(
        conn_id: ConnId,
        peer_features: Features,
        model_update_send: ModelUpdateSend,
    ) -> Self {
        Self {
            conn_id,

            peer_features,

            self_choking: AtomicBool::new(true),
            peer_choking: AtomicBool::new(true),

            self_interested: AtomicBool::new(false),
            peer_interested: AtomicBool::new(false),

            snubbing: AtomicBool::new(false),

            model_update_send,
        }
    }

    pub fn peer_features(&self) -> Features {
        self.peer_features
    }

    pub fn self_choking(&self) -> bool {
        self.self_choking.load(Ordering::SeqCst)
    }

    pub fn peer_choking(&self) -> bool {
        self.peer_choking.load(Ordering::SeqCst)
    }

    pub fn self_interested(&self) -> bool {
        self.self_interested.load(Ordering::SeqCst)
    }

    pub fn peer_interested(&self) -> bool {
        self.peer_interested.load(Ordering::SeqCst)
    }

    pub fn snubbing(&self) -> bool {
        self.snubbing.load(Ordering::SeqCst)
    }

    pub fn set_self_choking(&self, value: bool) -> bool {
        self.set(&self.self_choking, value, ModelUpdate::SelfChoking)
    }

    pub fn set_peer_choking(&self, value: bool) -> bool {
        self.set(&self.peer_choking, value, ModelUpdate::PeerChoking)
    }

    pub fn set_self_interested(&self, value: bool) -> bool {
        self.set(&self.self_interested, value, ModelUpdate::SelfInterested)
    }

    pub fn set_peer_interested(&self, value: bool) -> bool {
        self.set(&self.peer_interested, value, ModelUpdate::PeerInterested)
    }

    pub fn set_snubbing(&self, value: bool) -> bool {
        self.set(&self.snubbing, value, ModelUpdate::Snubbing)
    }

    fn set(&self, atomic: &AtomicBool, value: bool, f: fn(ConnId, bool) -> ModelUpdate) -> bool {
        if atomic.swap(value, Ordering::SeqCst) != value {
            self.model_update_send
                .send(|| f(self.conn_id.clone(), value));
            true
        } else {
            false
        }
    }
}
