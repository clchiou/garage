use std::io::Error;
use std::sync::{Arc, Mutex};

use clap::Args;
use tokio::signal;
use tokio::sync::Mutex as AsyncMutex;

use g1_base::sync::MutexExt;
use g1_tokio::task::{self, Joinable};

use bt_base::ConnId;
use bt_base::bitfield::BitsliceExt;
use bt_model::{Model, ModelUpdate};
use bt_peer::Manifold;
use bt_txrx::download::{Download, DownloadUpdate, Schedule};
use bt_txrx::push;

use crate::storage::StorageDir;

use super::{SELF_FEATURES, Txrx};

#[derive(Args, Debug)]
#[command(about = "Download a torrent from a peer")]
pub(crate) struct DownloadCommand {
    #[command(flatten)]
    storage_dir: StorageDir,

    #[command(flatten)]
    txrx: Txrx,
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

        let push_guard = push::spawn(SELF_FEATURES, model.clone(), manifold.clone());

        let (download, download_guard) = Download::spawn(
            model.clone(),
            manifold.clone(),
            Arc::new(AsyncMutex::new(storage)),
        );

        let mut guard = task::select([
            download_guard,
            push_guard.map(Ok).boxed(),
            manifold_guard
                .map(|result| result.map_err(Error::from))
                .boxed(),
        ]);

        tokio::select! {
            result = signal::ctrl_c() => {
                result?;
                tracing::info!("ctrl-c received!");
            }
            result = self.download(model, download, manifold) => {
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
        manifold: Manifold,
    ) -> Result<(), Error> {
        let mut download_update_recv = download.subscribe().expect("download");
        let mut model_update_recv = model.must_lock().subscribe();

        let args = self.txrx.handshake(self.txrx.make_stream().await?).await?;
        let conn_id = args.conn_id.clone();
        assert!(manifold.connect(args).await);

        let mut unchoke = false;
        let mut schedule = None;
        while !unchoke || schedule.is_none() {
            match model_update_recv.recv().await.map_err(Error::other)? {
                ModelUpdate::InitPeer(id) if id == conn_id => {
                    assert!(schedule.is_none());
                    schedule = Some(compute_schedule(&conn_id, &model.must_lock()));
                }
                ModelUpdate::PeerChoking(id, choking) if id == conn_id => {
                    if choking {
                        return Err(Error::other("peer choke"));
                    } else {
                        unchoke = true;
                    }
                }
                ModelUpdate::DisconnectPeer(id) if id == conn_id => {
                    return Err(Error::other("unexpected peer disconnect"));
                }
                _ => {}
            }
        }
        download.assign(schedule.expect("schedule")).await;

        tokio::select! {
            result = async {
                loop {
                    match model_update_recv.recv().await.map_err(Error::other)? {
                        ModelUpdate::PeerChoking(id, true) if id == conn_id => {
                            return Err(Error::other("peer choke"));
                        }
                        ModelUpdate::DisconnectPeer(id) if id == conn_id => {
                            return Err(Error::other("unexpected peer disconnect"));
                        }
                        _ => {}
                    }
                }
            } => result,

            result = async {
                while download_update_recv.recv().await.map_err(Error::other)?
                    != DownloadUpdate::ScheduleLen(0)
                {
                    // Nothing here.
                }
                Ok(())
            } => result,
        }
    }
}

fn compute_schedule(conn_id: &ConnId, model: &Model) -> Schedule {
    let torrent = model.torrents().get(conn_id.info_hash()).expect("torrent");
    let peer_pieces = torrent.get(&conn_id.conn_pair).expect("peer pieces");
    torrent
        .self_pieces()
        .iter_have_nots()
        .filter(|index| peer_pieces[usize::from(*index)])
        .map(|index| (conn_id.info_hash(), index, vec![conn_id.conn_pair]))
        .collect()
}
