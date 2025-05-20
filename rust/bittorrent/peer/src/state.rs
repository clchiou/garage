use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};

use tokio::sync::watch::{self, Receiver, Sender, error::RecvError};

use g1_tokio::sync::watch::Update;

#[derive(Debug)]
pub(crate) struct ConnStateUpper {
    /// True if we are choking the peer.
    pub(crate) self_choking: RwWatch,
    /// True if we are interested in the peer.
    pub(crate) self_interested: RwWatch,
    /// True if the peer is choking us.
    pub(crate) peer_choking: RoFlag,
    /// True if the peer is interested in us.
    pub(crate) peer_interested: RoFlag,
}

#[derive(Debug)]
pub(crate) struct ConnStateLower {
    pub(crate) self_choking: RoWatch,
    pub(crate) self_interested: RoWatch,
    pub(crate) peer_choking: RwFlag,
    pub(crate) peer_interested: RwFlag,
}

#[derive(Debug)]
pub(crate) struct RoFlag(Arc<AtomicBool>);

#[derive(Debug)]
pub(crate) struct RwFlag(Arc<AtomicBool>);

#[derive(Debug)]
pub(crate) struct RoWatch {
    recv: Receiver<bool>,
}

#[derive(Debug)]
pub(crate) struct RwWatch {
    recv: Receiver<bool>,
    send: Sender<bool>,
}

pub(crate) fn new_conn_state() -> (ConnStateUpper, ConnStateLower) {
    let (self_choking_ro, self_choking_rw) = new_watches(true);
    let (self_interested_ro, self_interested_rw) = new_watches(false);
    let (peer_choking_ro, peer_choking_rw) = new_flags(true);
    let (peer_interested_ro, peer_interested_rw) = new_flags(false);
    (
        ConnStateUpper {
            self_choking: self_choking_rw,
            self_interested: self_interested_rw,
            peer_choking: peer_choking_ro,
            peer_interested: peer_interested_ro,
        },
        ConnStateLower {
            self_choking: self_choking_ro,
            self_interested: self_interested_ro,
            peer_choking: peer_choking_rw,
            peer_interested: peer_interested_rw,
        },
    )
}

fn new_flags(init: bool) -> (RoFlag, RwFlag) {
    let flag = Arc::new(AtomicBool::new(init));
    (RoFlag(flag.clone()), RwFlag(flag))
}

fn new_watches(init: bool) -> (RoWatch, RwWatch) {
    let (send, recv) = watch::channel(init);
    (RoWatch { recv: recv.clone() }, RwWatch { recv, send })
}

impl RoFlag {
    pub(crate) fn get(&self) -> bool {
        self.0.load(Ordering::SeqCst)
    }
}

impl RwFlag {
    pub(crate) fn get(&self) -> bool {
        self.0.load(Ordering::SeqCst)
    }

    pub(crate) fn set(&self, value: bool) {
        self.0.store(value, Ordering::SeqCst);
    }
}

impl RoWatch {
    pub(crate) fn get(&self) -> bool {
        *self.recv.borrow()
    }

    pub(crate) async fn updated(&mut self) -> Result<bool, RecvError> {
        self.recv.changed().await?;
        Ok(*self.recv.borrow_and_update())
    }
}

impl RwWatch {
    pub(crate) fn get(&self) -> bool {
        *self.recv.borrow()
    }

    pub(crate) fn set(&self, value: bool) {
        self.send.update(value);
    }
}
