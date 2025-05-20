use std::io::Error;

use futures::future::{FutureExt, OptionFuture};

use g1_tokio::task::JoinQueue;

use bittorrent_base::InfoHash;
use bittorrent_dht::{Dht, DhtGuard};
use bittorrent_manager::{Manager, ManagerGuard};
use bittorrent_tracker::{Tracker, TrackerGuard};
use bittorrent_transceiver::{Transceiver, TransceiverGuard};
use bittorrent_utp::UtpSocket;

use crate::Mode;
use crate::init::{Guards, Init};
use crate::storage::StorageOpen;

#[derive(Debug)]
pub struct Actors {
    pub txrx: Transceiver,
    txrx_guard: TransceiverGuard,

    pub manager: Manager,
    manager_guard: ManagerGuard,

    pub dht_ipv4: Option<Dht>,
    pub dht_ipv6: Option<Dht>,
    dht_guard_ipv4: Option<DhtGuard>,
    dht_guard_ipv6: Option<DhtGuard>,

    pub tracker: Option<Tracker>,
    tracker_guard: Option<TrackerGuard>,

    utp_socket_ipv4: Option<UtpSocket>,
    utp_socket_ipv6: Option<UtpSocket>,

    tasks: JoinQueue<Result<(), Error>>,
}

impl Actors {
    pub async fn spawn(mode: Mode, info_hash: InfoHash, open: StorageOpen) -> Result<Self, Error> {
        let mut init = Init::new(mode, info_hash, open);
        let manager = init.init_manager().await?;
        let dht_ipv4 = init.init_dht_ipv4().await?;
        let dht_ipv6 = init.init_dht_ipv6().await?;
        let tracker = init.init_tracker().await?;

        // Spawn txrx at last.
        let txrx = init.init_txrx().await?;

        let Guards {
            txrx_guard,
            manager_guard,
            dht_guard_ipv4,
            dht_guard_ipv6,
            tracker_guard,
            utp_socket_ipv4,
            utp_socket_ipv6,
            tasks,
        } = init.into_guards().await?;

        Ok(Self {
            txrx,
            txrx_guard,

            manager,
            manager_guard,

            dht_ipv4,
            dht_ipv6,
            dht_guard_ipv4,
            dht_guard_ipv6,

            tracker,
            tracker_guard,

            utp_socket_ipv4,
            utp_socket_ipv6,

            tasks,
        })
    }

    pub async fn join_any(&mut self) {
        macro_rules! call {
            ($guard:ident, $func:ident $(,)?) => {
                OptionFuture::from(self.$guard.as_mut().map(|guard| guard.$func()))
            };
        }
        tokio::select! {
            () = self.txrx_guard.join() => {}
            () = self.manager_guard.join() => {}
            Some(()) = call!(dht_guard_ipv4, joinable) => {}
            Some(()) = call!(dht_guard_ipv6, joinable) => {}
            Some(()) = call!(tracker_guard, join) => {}
            Some(()) = call!(utp_socket_ipv4, join) => {}
            Some(()) = call!(utp_socket_ipv6, join) => {}
            () = self.tasks.joinable() => {}
        }
    }

    pub async fn shutdown_all(&mut self) -> Result<(), Error> {
        macro_rules! shutdown {
            ($guard:ident, $mapper:expr $(,)?) => {
                OptionFuture::from(self.$guard.as_mut().map(|guard| guard.shutdown()))
                    .map(|result| result.map($mapper).unwrap_or(Ok(())))
            };
        }
        let results = <[_; 8]>::from(tokio::join!(
            self.txrx_guard.shutdown().map(|r| r?),
            self.manager_guard.shutdown().map(|r| r?),
            shutdown!(dht_guard_ipv4, |r| r?),
            shutdown!(dht_guard_ipv6, |r| r?),
            shutdown!(tracker_guard, |r| r?.map_err(Error::other)),
            shutdown!(utp_socket_ipv4, |r| r),
            shutdown!(utp_socket_ipv6, |r| r),
            self.tasks.shutdown().map(|r| r?),
        ));
        let mut first_error_result = Ok(());
        for result in results {
            if result.is_err() {
                match first_error_result {
                    Ok(()) => first_error_result = result,
                    Err(_) => tracing::warn!(error = %result.unwrap_err(), "actor error"),
                }
            }
        }
        first_error_result
    }
}
