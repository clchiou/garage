use bt_base::InfoHash;
use bt_model::fold::{self, Consumer, Fold};
use bt_model::{Model, ModelUpdate};

struct TorrentChange {
    info_hash: InfoHash,
    state: Option<bool>,
}

pub(crate) type TorrentChangeConsumer = Consumer<bool>;

pub(crate) use bt_model::fold::{Closed, FoldGuard as TorrentChangeGuard};

pub(crate) fn spawn(
    model: &Model,
    info_hash: InfoHash,
) -> (TorrentChangeConsumer, TorrentChangeGuard) {
    let state = if model.torrents().contains(info_hash.clone()) {
        Some(true)
    } else {
        None
    };
    fold::spawn(TorrentChange { info_hash, state }, model.subscribe())
}

impl Fold for TorrentChange {
    type Value = bool;

    fn fold(&mut self, value: &mut Option<Self::Value>, update: ModelUpdate) {
        match update {
            ModelUpdate::InitTorrent(info_hash) if info_hash == self.info_hash => {
                match self.state {
                    None => {
                        self.state = Some(true);
                        *value = Some(true);
                    }
                    Some(true) => panic!("unexpected torrent init"),
                    // We record only the first init; re-inits are ignored for now.
                    Some(false) => {}
                }
            }
            ModelUpdate::RemoveTorrent(info_hash) if info_hash == self.info_hash => {
                match self.state {
                    None => panic!("unexpected torrent removal"),
                    Some(true) => {
                        self.state = Some(false);
                        *value = Some(false);
                    }
                    // Ditto.
                    Some(false) => {}
                }
            }
            // Other updates are irrelevant to us.
            _ => {}
        }
    }
}
