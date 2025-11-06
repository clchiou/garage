use std::io;
use std::mem;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use futures::sink::SinkExt;
use futures::stream::TryStreamExt;
use snafu::prelude::*;
use tokio::sync::mpsc::{self, Receiver};
use tokio::time::{self, Interval};

use g1_base::sync::MutexExt;
use g1_tokio::task::{Cancel, JoinGuard};

use bt_base::bitfield::BitfieldExt;
use bt_base::{Bitfield, BlockRange, ConnId};
use bt_model::{ConnState, Model, PeerStat, TorrentStat};
use bt_proto::message::Checker;
use bt_proto::{BoxSink, BoxStream, Message};

use crate::error::{ConnActorError, Error, IoSnafu, MessageSnafu};
use crate::half_open::Backlog;
use crate::model::{self, Closed, TorrentChangeConsumer, TorrentChangeGuard};
use crate::{ConnArgs, PeerMessage, PeerMessageSend};

//
// I am not sure if this is a good idea, but I run `recv` and `send` concurrently at the cost of
// added complexity.
//

#[derive(Clone, Debug)]
pub struct Conn {
    cancel: Cancel,
    stub: ConnSenderStub,
}

pub(crate) type ConnGuard = JoinGuard<Result<(), Error>>;

struct ConnActor {
    conn_id: ConnId,

    model: Arc<Mutex<Model>>,

    torrent_change: TorrentChangeConsumer,
    torrent_change_guard: TorrentChangeGuard,

    peer_message_send: PeerMessageSend,
}

struct ConnReceiver {
    conn_id: ConnId,

    stream: BoxStream,

    model: Arc<Mutex<Model>>,

    checker: Checker,

    peer_message_send: PeerMessageSend,

    conn_state: ConnState,
    torrent_stat: TorrentStat,
    peer_stat: PeerStat,

    backlog: Backlog,
}

struct ConnSender {
    sink: BoxSink,

    checker: Checker,

    keepalive: Interval,

    conn_state: ConnState,
    torrent_stat: TorrentStat,
    peer_stat: PeerStat,
}

// TODO: Make this configurable.
const KEEPALIVE_TIMEOUT: Duration = Duration::from_secs(120);

impl Conn {
    pub(crate) fn spawn(
        args: ConnArgs,
        backlog: Backlog,
        model: Arc<Mutex<Model>>,
        peer_message_send: PeerMessageSend,
    ) -> Result<(Self, ConnGuard), ConnArgs> {
        let torrent_change;
        let torrent_change_guard;
        let conn_state;
        let layout;
        let torrent_stat;
        let peer_stat;
        {
            let mut model = model.must_lock();
            if !model.torrents().contains(args.conn_id.info_hash()) {
                return Err(args);
            }

            (torrent_change, torrent_change_guard) = model::spawn(&model, args.conn_id.info_hash());

            model.connect_peer(args.conn_id.clone(), args.peer_features);

            conn_state = model.conn_states().get(&args.conn_id).expect("conn state");

            let torrent = model
                .torrents_mut()
                .get(args.conn_id.info_hash())
                .expect("torrent");
            layout = torrent.layout().clone();
            torrent_stat = torrent.stat();
            peer_stat = torrent
                .peer_stats()
                .get(&args.conn_id.conn_pair)
                .expect("peer stat");
        }

        let ConnArgs {
            conn_id,
            self_features,
            peer_features,
            stream,
            sink,
        } = args;

        let checker = Checker::new(self_features, peer_features, layout);

        let mut keepalive = time::interval(KEEPALIVE_TIMEOUT);
        keepalive.reset();

        let mut actor = ConnActor {
            conn_id: conn_id.clone(),

            model: model.clone(),

            torrent_change,
            torrent_change_guard,

            peer_message_send: peer_message_send.clone(),
        };

        let receiver = ConnReceiver {
            conn_id,

            stream,

            model,

            checker: checker.clone(),

            peer_message_send,

            conn_state: conn_state.clone(),
            torrent_stat: torrent_stat.clone(),
            peer_stat: peer_stat.clone(),

            backlog,
        };

        let (sender_send, sender_recv) = mpsc::channel(16);
        let stub = ConnSenderStub::new(sender_send);
        let sender = ConnSender {
            sink,

            checker,

            keepalive,

            conn_state,
            torrent_stat,
            peer_stat,
        };

        let guard = ConnGuard::spawn(move |cancel| async move {
            actor.run(cancel, receiver, sender, sender_recv).await
        });

        Ok((
            Self {
                cancel: guard.cancel_handle(),
                stub,
            },
            guard,
        ))
    }

    pub fn disconnect(&self) {
        self.cancel.set();
    }

    pub async fn send(&self, message: Message) {
        self.stub.send(message).await
    }
}

impl ConnActor {
    async fn run(
        &mut self,
        cancel: Cancel,
        receiver: ConnReceiver,
        mut sender: ConnSender,
        sender_recv: Receiver<ConnSenderMessage>,
    ) -> Result<(), Error> {
        let mut result = self.startup().await;
        match result {
            Ok(()) => {
                let recv_guard = receiver.spawn(cancel.clone());
                let send_guard = sender.spawn(cancel, sender_recv);
                result = self.run_concurrent(recv_guard, send_guard).await;
            }
            Err(_) => {
                if let Err(error) = sender.sink.close().await {
                    tracing::warn!(conn_id = %self.conn_id, %error, "sink close");
                }
            }
        }
        self.shutdown(result).await
    }

    async fn run_concurrent(
        &mut self,
        mut recv_guard: JoinGuard<Result<(), ConnActorError>>,
        mut send_guard: JoinGuard<Result<(), io::Error>>,
    ) -> Result<(), ConnActorError> {
        tokio::select! {
            change = self.torrent_change.consume() => {
                // When we started, the torrent had been initialized, so the only possible change
                // is its removal.
                assert!(matches!(change, Ok(false) | Err(Closed)));
            }
            () = &mut recv_guard => {}
            () = &mut send_guard => {}
        }
        let (recv_result, send_result) = tokio::join!(recv_guard.shutdown(), send_guard.shutdown());

        let conn_id = &self.conn_id;
        let recv_result = match recv_result {
            Ok(result) => result,
            Err(error) => {
                // Right now, we return `Ok`.  Should we return `Err` instead?  If so, what kind?
                tracing::warn!(%conn_id, %error, "peer recv shutdown");
                Ok(())
            }
        };
        let send_result = match send_result {
            Ok(result) => result,
            Err(error) => {
                // Right now, we return `Ok`.  Should we return `Err` instead?  If so, what kind?
                tracing::warn!(%conn_id, %error, "peer send shutdown");
                Ok(())
            }
        };

        // `recv_result`, which may be a broadcast error, takes precedence over `send_result`.
        recv_result.and(send_result.context(IoSnafu))
    }

    async fn startup(&self) -> Result<(), ConnActorError> {
        tracing::info!(conn_id = %self.conn_id, "peer connected");
        self.peer_message_send
            .actor_send(PeerMessage::Connect(self.conn_id.clone()))
            .await
    }

    async fn shutdown(&mut self, result: Result<(), ConnActorError>) -> Result<(), Error> {
        let conn_id = &self.conn_id;
        match &result {
            Ok(()) => tracing::info!(%conn_id, "peer disconnected"),
            Err(error) => tracing::warn!(%conn_id, %error, "peer disconnected"),
        }

        self.model.must_lock().disconnect_peer(&self.conn_id);

        let result = match result {
            Ok(()) => Ok(()),
            Err(error) => Err(Arc::new(error.into_broadcast()?)),
        };
        self.peer_message_send
            .send(PeerMessage::Disconnect(self.conn_id.clone(), result))
            .await?;

        if let Err(error) = self.torrent_change_guard.shutdown().await {
            tracing::warn!(%conn_id, %error, "torrent change shutdown");
        }

        Ok(())
    }
}

#[g1_actor::actor(
    loop_(
        type Result<(), ConnActorError>,
        run(run_impl),
        return Ok(()),
    )
)]
impl ConnReceiver {
    fn spawn(self, cancel: Cancel) -> JoinGuard<Result<(), ConnActorError>> {
        let mut loop_ = ConnReceiverLoop::new(cancel.clone(), self);
        JoinGuard::new(tokio::spawn(async move { loop_.run().await }), cancel)
    }

    async fn startup(&mut self) -> Result<(), ConnActorError> {
        for message in mem::take(&mut self.backlog) {
            self.recv(message).await?;
        }
        Ok(())
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
}

impl ConnReceiverLoop {
    async fn run(&mut self) -> Result<(), ConnActorError> {
        self.__actor.startup().await?;
        self.run_impl().await
    }
}

#[g1_actor::actor(
    stub(spawn(skip)),
    loop_(
        type Result<(), io::Error>,
        return self.sink.close().await,
    ),
)]
impl ConnSender {
    fn spawn(
        self,
        cancel: Cancel,
        sender_recv: Receiver<ConnSenderMessage>,
    ) -> JoinGuard<Result<(), io::Error>> {
        let mut loop_ = ConnSenderLoop::new(cancel.clone(), sender_recv, self);
        JoinGuard::new(tokio::spawn(async move { loop_.run().await }), cancel)
    }

    #[actor::method(
        return { let result: () = result?; },
        stub(return {
            let result: () = {
                if let Err(message) = result {
                    tracing::warn!(?message, "drop outgoing message");
                }
            };
        }),
    )]
    async fn send(&mut self, message: Message) -> Result<(), io::Error> {
        self.checker.check(&message).expect("message");

        // For simplicity, we update the model before sending the message.  If `send` fails, the
        // stats may be slightly inaccurate.
        self.update_model_by_self_message(&message);

        self.sink.send(message).await?;
        self.keepalive.reset();

        Ok(())
    }

    #[actor::loop_(react = {
        let _ = self.keepalive.tick();
        self.send_keepalive().await?;
    })]
    async fn send_keepalive(&mut self) -> Result<(), io::Error> {
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
}
