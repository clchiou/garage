use std::collections::{BTreeMap, BTreeSet};
use std::io::Error;
use std::sync::{Arc, Mutex};

use clap::Args;
use tokio::signal;
use tokio::sync::Mutex as AsyncMutex;

use g1_base::sync::MutexExt;
use g1_tokio::task::{self, Joinable};

use bt_base::bitfield::BitsliceExt;
use bt_base::{ConnId, ConnPair, InfoHash, PieceIndex};
use bt_model::{Model, ModelUpdate};
use bt_net::Net;
use bt_peer::Manifold;
use bt_txrx::download::{Download, Schedule};
use bt_txrx::push;

use crate::storage::StorageDir;

use super::{Endpoints, SELF_FEATURES, Txrx};

#[derive(Args, Debug)]
#[command(about = "Download a torrent from peers")]
pub(crate) struct DownloadCommand {
    #[command(flatten)]
    storage_dir: StorageDir,

    #[command(flatten)]
    txrx: Txrx,

    #[command(flatten)]
    endpoints: Endpoints,
}

impl DownloadCommand {
    pub(crate) async fn run(&self) -> Result<(), Error> {
        let storage = self.storage_dir.open(false)?;

        let model = self.txrx.make_model(&storage)?;
        {
            let model = model.must_lock();
            if model
                .torrents()
                .get(self.txrx.info_hash.clone())
                .expect("torrent")
                .self_pieces()
                .all()
            {
                tracing::info!("complete torrent");
                return Ok(());
            }
        }

        let (manifold, manifold_guard) = Manifold::spawn(model.clone());

        let (net, net_guard) = self.txrx.spawn_net(model.clone(), manifold.clone());

        let push_guard = push::spawn(SELF_FEATURES, model.clone(), manifold.clone());

        let (download, download_guard) =
            Download::spawn(model.clone(), manifold, Arc::new(AsyncMutex::new(storage)));

        let mut guard = task::select([
            download_guard,
            push_guard.map(Ok).boxed(),
            manifold_guard
                .map(|result| result.map_err(Error::from))
                .boxed(),
            net_guard.boxed(),
        ]);

        tokio::select! {
            result = signal::ctrl_c() => {
                result?;
                tracing::info!("ctrl-c received!");
            }
            result = self.download(model, download, net) => {
                result?;
            }
            () = &mut guard => {
                tracing::warn!("unexpected manifold exit");
            }
        }
        guard.shutdown().await?
    }

    async fn download(
        &self,
        model: Arc<Mutex<Model>>,
        download: Download,
        net: Net,
    ) -> Result<(), Error> {
        let mut schedule;
        let mut model_update_recv;
        {
            let model = model.must_lock();
            schedule = model
                .torrents()
                .get(self.txrx.info_hash.clone())
                .expect("torrent")
                .self_pieces()
                .iter_have_nots()
                .map(|index| ((self.txrx.info_hash.clone(), index), BTreeSet::new()))
                .collect::<BTreeMap<_, _>>();
            model_update_recv = model.subscribe();
        }

        self.endpoints
            .init(self.txrx.info_hash.clone(), model.clone(), net)
            .await?;

        while !schedule.is_empty() {
            match model_update_recv.recv().await.map_err(Error::other)? {
                ModelUpdate::InitPeer(conn_id) => {
                    let sched = compute_schedule(&mut schedule, &conn_id, &model.must_lock());
                    download.assign(sched).await;
                }
                ModelUpdate::SetPeerPiece(conn_id, index) => {
                    if let Some(sched) = update_schedule(&mut schedule, &conn_id, index) {
                        download.assign(sched).await;
                    }
                }
                ModelUpdate::SetSelfPiece(info_hash, index) => {
                    schedule.remove(&(info_hash, index));
                }
                ModelUpdate::PeerChoking(conn_id, choking) => {
                    tracing::info!(%conn_id, choking);
                }
                _ => {}
            }
        }
        tracing::info!("download complete");
        Ok(())
    }
}

fn compute_schedule(
    schedule: &mut BTreeMap<(InfoHash, PieceIndex), BTreeSet<ConnPair>>,
    conn_id: &ConnId,
    model: &Model,
) -> Schedule {
    let torrent = model.torrents().get(conn_id.info_hash()).expect("torrent");
    let peer_pieces = torrent.get(&conn_id.conn_pair).expect("peer pieces");
    for index in peer_pieces.iter_haves() {
        if let Some(candidates) = schedule.get_mut(&(conn_id.info_hash(), index)) {
            candidates.insert(conn_id.conn_pair);
        }
    }
    to_schedule(schedule)
}

fn update_schedule(
    schedule: &mut BTreeMap<(InfoHash, PieceIndex), BTreeSet<ConnPair>>,
    conn_id: &ConnId,
    index: PieceIndex,
) -> Option<Schedule> {
    schedule
        .get_mut(&(conn_id.info_hash(), index))?
        .insert(conn_id.conn_pair)
        .then(|| to_schedule(schedule))
}

fn to_schedule(schedule: &BTreeMap<(InfoHash, PieceIndex), BTreeSet<ConnPair>>) -> Schedule {
    schedule
        .iter()
        .map(|((info_hash, index), candidates)| {
            (
                info_hash.clone(),
                *index,
                candidates.iter().copied().collect(),
            )
        })
        .collect()
}
