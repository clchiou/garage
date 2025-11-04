use bt_base::{ConnPair, InfoHash, PieceIndex};

// NOTE: The caller must ensure that `(InfoHash, PieceIndex)` are unique.
pub type Schedule = Vec<(InfoHash, PieceIndex, Vec<ConnPair>)>;

pub(super) trait ScheduleExt {
    fn remove_piece(&mut self, info_hash: InfoHash, index: PieceIndex);

    fn remove_torrent(&mut self, info_hash: InfoHash);
}

impl ScheduleExt for Schedule {
    fn remove_piece(&mut self, info_hash: InfoHash, index: PieceIndex) {
        remove_if(self, |hash, i| hash == &info_hash && i == index);
    }

    fn remove_torrent(&mut self, info_hash: InfoHash) {
        remove_if(self, |hash, _| hash == &info_hash);
    }
}

fn remove_if<F>(schedule: &mut Schedule, f: F)
where
    F: Fn(&InfoHash, PieceIndex) -> bool,
{
    schedule.retain(|(info_hash, index, _)| !f(info_hash, *index));
}
