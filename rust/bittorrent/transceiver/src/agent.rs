use std::io::{Error, ErrorKind};
use std::sync::Arc;

use bytes::Bytes;
use tokio::{
    sync::{
        broadcast::{self, error::RecvError, Receiver},
        Mutex, Notify,
    },
    task::JoinHandle,
};

use g1_tokio::task::{self, JoinTaskError};

use bittorrent_base::Dimension;
use bittorrent_dht::Agent as DhtAgent;
use bittorrent_manager::Manager;
use bittorrent_peer::Recvs;

use crate::{
    actor::{Actor, DynStorage, Update},
    stat::Torrent,
};

#[derive(Debug)]
pub struct Init {
    pub torrent: Torrent,
    update_recv: Receiver<Update>,
    exit: Arc<Notify>,
    actor: Actor,
}

#[derive(Debug)]
pub struct Agent {
    pub torrent: Torrent,
    update_recv: Receiver<Update>,
    exit: Arc<Notify>,
    task: Mutex<JoinHandle<Result<(), Error>>>,
}

impl Init {
    pub async fn make(
        raw_info: Bytes,
        dim: Dimension,
        manager: Arc<Manager>,
        recvs: Recvs,
        storage: DynStorage,
        dht_ipv4: Option<Arc<DhtAgent>>,
        dht_ipv6: Option<Arc<DhtAgent>>,
    ) -> Result<Self, Error> {
        let exit = Arc::new(Notify::new());
        let (update_send, update_recv) = broadcast::channel(*crate::update_queue_size());
        let actor = Actor::make(
            exit.clone(),
            raw_info,
            dim,
            manager,
            recvs,
            storage,
            dht_ipv4,
            dht_ipv6,
            update_send,
        )
        .await?;
        let torrent = Torrent::new(actor.torrent.clone());
        Ok(Self {
            torrent,
            update_recv,
            exit,
            actor,
        })
    }

    pub fn subscribe(&self) -> Receiver<Update> {
        self.update_recv.resubscribe()
    }
}

impl From<Init> for Agent {
    fn from(init: Init) -> Self {
        let Init {
            torrent,
            update_recv,
            exit,
            actor,
        } = init;
        Self {
            torrent,
            update_recv,
            exit,
            task: Mutex::new(tokio::spawn(actor.run())),
        }
    }
}

impl Agent {
    pub fn subscribe(&self) -> Receiver<Update> {
        self.update_recv.resubscribe()
    }

    pub async fn join(&self) {
        let mut update_recv = self.update_recv.resubscribe();
        while !matches!(update_recv.recv().await, Err(RecvError::Closed)) {
            // Nothing to do here.
        }
    }

    pub fn close(&self) {
        self.exit.notify_one();
    }

    pub async fn shutdown(&self) -> Result<(), Error> {
        self.close();
        task::join_task(&self.task, *crate::grace_period())
            .await
            .map_err(|error| match error {
                JoinTaskError::Cancelled => Error::other("transceiver actor is cancelled"),
                JoinTaskError::Timeout => Error::new(
                    ErrorKind::TimedOut,
                    "transceiver shutdown grace period is exceeded",
                ),
            })?
    }
}

impl Drop for Agent {
    fn drop(&mut self) {
        self.task.get_mut().abort();
    }
}
