use std::mem;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use futures::sink::SinkExt;
use futures::stream::TryStreamExt;
use snafu::prelude::*;
use tokio::sync::broadcast::error::RecvError;
use tokio::time::{self, Interval};

use g1_base::sync::MutexExt;
use g1_tokio::task::JoinGuard;

use bt_base::bitfield::BitfieldExt;
use bt_base::{Bitfield, BlockRange, ConnId};
use bt_model::{ConnState, Model, ModelUpdate, ModelUpdateRecv, PeerStat, TorrentStat};
use bt_proto::message::Checker;
use bt_proto::{BoxSink, BoxStream, Message};

use crate::error::{ConnActorError, Error, IoSnafu, MessageSnafu};
use crate::half_open::Backlog;
use crate::{ConnArgs, PeerMessage, PeerMessageSend};

struct ConnActor {
    conn_id: ConnId,

    stream: BoxStream,
    sink: BoxSink,

    model: Arc<Mutex<Model>>,
    model_update_recv: ModelUpdateRecv,

    checker: Checker,

    peer_message_send: PeerMessageSend,

    keepalive: Interval,

    conn_state: ConnState,
    torrent_stat: TorrentStat,
    peer_stat: PeerStat,

    backlog: Backlog,
}

pub(crate) type ConnGuard = JoinGuard<Result<(), Error>>;

// TODO: Make this configurable.
const KEEPALIVE_TIMEOUT: Duration = Duration::from_secs(120);

#[g1_actor::actor(
    stub(
        pub, Conn,
        spawn(spawn_impl),
        cancel(pub, disconnect),
    ),
    loop_(
        type Result<(), Error>,
        run(run_impl, type Result<(), ConnActorError>),
        return Ok(()),
    ),
)]
impl ConnActor {
    // True if torrent is removed.
    async fn startup(&mut self) -> Result<bool, ConnActorError> {
        tracing::info!(conn_id = %self.conn_id, "peer connected");

        self.peer_message_send
            .actor_send(PeerMessage::Connect(self.conn_id.clone()))
            .await?;

        if !self
            .model
            .must_lock()
            .torrents()
            .contains(self.conn_id.info_hash())
        {
            return Ok(true);
        }

        for message in mem::take(&mut self.backlog) {
            self.recv(message).await?;
        }

        Ok(false)
    }

    #[actor::loop_(react = {
        let update = self.model_update_recv.recv();
        if self.is_torrent_removed(update) {
            break;
        }
    })]
    fn is_torrent_removed(&self, update: Result<ModelUpdate, RecvError>) -> bool {
        match update {
            Ok(ModelUpdate::InitTorrent(info_hash)) => {
                if info_hash == self.conn_id.info_hash {
                    // This should not happen because we have subscribed to model changes and
                    // verified the model state.  Should we crash in this case?
                    tracing::error!(conn_id = %self.conn_id, "unexpected torrent init");

                    // Treat this as if the torrent were removed.
                    true
                } else {
                    false
                }
            }

            Ok(ModelUpdate::RemoveTorrent(info_hash)) => info_hash == self.conn_id.info_hash,

            // Other updates are irrelevant to us.
            Ok(_) => false,

            Err(RecvError::Lagged(lag)) => {
                // If we are lagging behind multiple updates, we may have missed a torrent's
                // removal and re-initialization.  In that case, the `Torrent` value is empty and
                // we should reconnect to receive the peer's bitfield again.
                tracing::error!(conn_id = %self.conn_id, lag, "lagging behind");

                !self
                    .model
                    .must_lock()
                    .torrents()
                    .contains(self.conn_id.info_hash())
            }

            // Treat this as if the torrent were removed.
            Err(RecvError::Closed) => true,
        }
    }

    #[actor::loop_(react = {
        let message = self.stream.try_next();
        match message.context(MessageSnafu)? {
            Some(message) => self.recv(message).await?,
            None => break,
        }
    })]
    async fn recv(&self, message: Message) -> Result<(), ConnActorError> {
        self.checker.check(&message).context(MessageSnafu)?;

        self.update_model_by_peer_message(&message);

        self.peer_message_send
            .actor_send(PeerMessage::Message(self.conn_id.clone(), message))
            .await
    }

    #[actor::method(
        pub,
        return { let result: () = result?; },
        stub(return {
            let result: () = {
                if let Err(message) = result {
                    tracing::warn!(?message, "drop outgoing message");
                }
            };
        }),
    )]
    async fn send(&mut self, message: Message) -> Result<(), ConnActorError> {
        self.checker.check(&message).expect("message");

        // For simplicity, we update the model before sending the message.  If `send` fails, the
        // stats may be slightly inaccurate.
        self.update_model_by_self_message(&message);

        self.sink.send(message).await.context(IoSnafu)?;
        self.keepalive.reset();

        Ok(())
    }

    #[actor::loop_(react = {
        let _ = self.keepalive.tick();
        self.send_keepalive().await?;
    })]
    async fn send_keepalive(&mut self) -> Result<(), ConnActorError> {
        self.send(Message::KeepAlive).await
    }

    // The direction of data flow could go either way: We could subscribe to model changes and send
    // corresponding messages, or check the messages and update the model.  For now, we have chosen
    // the latter, though frankly, I am not sure which approach is better.
    fn update_model_by_self_message(&self, message: &Message) {
        match message {
            Message::Choke => {
                self.conn_state.set_self_choking(true);
            }
            Message::Unchoke => {
                self.conn_state.set_self_choking(false);
            }
            Message::Interested => {
                self.conn_state.set_self_interested(true);
            }
            Message::NotInterested => {
                self.conn_state.set_self_interested(false);
            }

            Message::Piece(BlockRange(_, _, size), _) => {
                let size = *size;
                self.torrent_stat.upload_add(size);
                self.peer_stat.send_add(size);
            }

            _ => {}
        }
    }

    fn update_model_by_peer_message(&self, message: &Message) {
        match message {
            Message::Choke => {
                self.conn_state.set_peer_choking(true);
            }
            Message::Unchoke => {
                self.conn_state.set_peer_choking(false);
            }
            Message::Interested => {
                self.conn_state.set_peer_interested(true);
            }
            Message::NotInterested => {
                self.conn_state.set_peer_interested(false);
            }

            Message::Bitfield(bitfield) => {
                self.insert_peer_pieces(|num_pieces| {
                    Bitfield::try_from_bytes(bitfield, num_pieces).expect("bitfield")
                });
            }
            Message::HaveAll => {
                self.insert_peer_pieces(|num_pieces| Bitfield::repeat(true, num_pieces));
            }
            Message::HaveNone => {
                self.insert_peer_pieces(|num_pieces| Bitfield::repeat(false, num_pieces));
            }
            Message::Have(index) => {
                if let Some(torrent) = self
                    .model
                    .must_lock()
                    .torrents_mut()
                    .get_mut(self.conn_id.info_hash())
                {
                    torrent.set_peer_piece(&self.conn_id.conn_pair, *index);
                }
            }

            Message::Piece(BlockRange(_, _, size), _) => {
                let size = *size;
                self.torrent_stat.download_add(size);
                self.peer_stat.recv_add(size);
            }

            _ => {}
        }
    }

    fn insert_peer_pieces<F>(&self, f: F)
    where
        F: FnOnce(usize) -> Bitfield,
    {
        if let Some(torrent) = self
            .model
            .must_lock()
            .torrents_mut()
            .get_mut(self.conn_id.info_hash())
        {
            torrent.insert(self.conn_id.conn_pair, f(torrent.self_pieces().len()));
        }
    }

    async fn shutdown(&mut self, mut result: Result<(), ConnActorError>) -> Result<(), Error> {
        if !matches!(result, Err(ConnActorError::Io { .. })) {
            result = result.and(self.sink.close().await.context(IoSnafu));
        }

        let conn_id = &self.conn_id;
        match &result {
            Ok(()) => tracing::info!(%conn_id, "peer disconnected"),
            Err(error) => tracing::warn!(%conn_id, %error, "peer disconnected"),
        }

        {
            self.model.must_lock().disconnect_peer(&self.conn_id);

            // We do not remove `peer_stat` from `model` because we attempt to reconnect to the
            // peer and want to preserve it.  It will be removed if the reconnection fails.
        }

        let result = match result {
            Ok(()) => Ok(()),
            Err(error) => Err(Arc::new(error.into_broadcast()?)),
        };
        self.peer_message_send
            .send(PeerMessage::Disconnect(self.conn_id.clone(), result))
            .await
    }
}

impl ConnActorLoop {
    async fn run(&mut self) -> Result<(), Error> {
        let result = match self.__actor.startup().await {
            Ok(true) => Ok(()),
            Ok(false) => self.run_impl().await,
            Err(error) => Err(error),
        };
        self.__actor.shutdown(result).await
    }
}

impl Conn {
    pub(crate) fn spawn(
        args: ConnArgs,
        backlog: Backlog,
        model: Arc<Mutex<Model>>,
        peer_message_send: PeerMessageSend,
    ) -> Result<(Self, ConnGuard), ConnArgs> {
        let conn_state;
        let layout;
        let torrent_stat;
        let peer_stat;
        let model_update_recv;
        {
            let mut model = model.must_lock();

            if !model.torrents().contains(args.conn_id.info_hash()) {
                return Err(args);
            }

            model.connect_peer(args.conn_id.clone(), args.peer_features);

            conn_state = model.conn_states().get(&args.conn_id).expect("conn state");

            let torrent = model
                .torrents_mut()
                .get_mut(args.conn_id.info_hash())
                .expect("torrent");
            layout = torrent.layout().clone();
            torrent_stat = torrent.stat();

            peer_stat = torrent
                .peer_stats_mut()
                .get_or_insert_default(args.conn_id.conn_pair);

            model_update_recv = model.subscribe();
        }

        let ConnArgs {
            conn_id,
            self_features,
            peer_features,
            stream,
            sink,
        } = args;

        let mut keepalive = time::interval(KEEPALIVE_TIMEOUT);
        keepalive.reset();

        Ok(Self::spawn_impl(ConnActor {
            conn_id,

            stream,
            sink,

            model,
            model_update_recv,

            checker: Checker::new(self_features, peer_features, layout),

            peer_message_send,

            keepalive,

            conn_state,
            torrent_stat,
            peer_stat,

            backlog,
        }))
    }
}
