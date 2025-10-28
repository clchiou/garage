use std::sync::{Arc, Mutex};

use bytes::Bytes;
use futures::sink::SinkExt;
use futures::stream::TryStreamExt;
use snafu::prelude::*;

use g1_base::sync::MutexExt;
use g1_tokio::task::JoinGuard;

use bt_base::Features;
use bt_model::Model;
use bt_proto::Message;
use bt_proto::message;

use crate::ConnArgs;
use crate::error::{BacklogSnafu, ConnActorError, Error, IoSnafu, MessageSnafu};
use crate::model::{self, TorrentChangeConsumer, TorrentChangeGuard};

use super::{Backlog, HalfOpenMessage, HalfOpenMessageSend};

struct ConnActor {
    args: ConnArgs,

    torrent_change: TorrentChangeConsumer,
    torrent_change_guard: TorrentChangeGuard,

    half_open_message_send: HalfOpenMessageSend,
    // We temporarily store messages in a backlog until the torrent is initialized.
    backlog: Backlog,
}

pub(super) type HalfOpenResult = Result<Option<(ConnArgs, Backlog)>, Error>;

pub(super) type HalfOpenConnGuard = JoinGuard<HalfOpenResult>;

// TODO: Make this configurable.
const BACKLOG_LIMIT: usize = 64;

#[g1_actor::actor(
    stub(
        pub, HalfOpenConn, struct {
            self_features: Features,
            peer_features: Features,
        },
        spawn(spawn_impl),
        cancel(pub, disconnect),
    ),
    loop_(
        type HalfOpenResult,
        run(run_impl, type Result<(), ConnActorError>),
        // We exit whether the torrent is initialized or removed.  (In the latter case, the
        // initialization was missed.)
        react = {
            let _ = self.torrent_change.consume();
            break;
        },
        return Ok(()),
    ),
)]
impl ConnActor {
    async fn startup(&self) -> Result<(), ConnActorError> {
        tracing::info!(conn_id = %self.args.conn_id, "half-open peer connected");
        self.half_open_message_send
            .actor_send(HalfOpenMessage::Connect(self.args.conn_id.clone()))
            .await
    }

    //
    // TODO: The actor does not execute `recv` and `send` concurrently.  Hypothetically, this could
    // lead to a deadlock: the actor may be executing `recv` and become blocked while broadcasting
    // incoming messages, while the broadcast receivers are blocked while sending outgoing messages
    // to `send`.  Since both the actor and the receivers are blocked, they cannot handle any
    // messages sent to them, resulting in a deadlock.  If this scenario occurs, we will need to
    // make the actor execute `recv` and `send` concurrently.
    //

    // TODO: This design is flawed, as the caller cannot determine whether an extension message has
    // been replayed from the backlog.  A redesign is required.
    #[actor::loop_(react = {
        let message = self.args.stream.try_next();
        match message.context(MessageSnafu)? {
            Some(message) => self.recv(message).await?,
            None => break,
        }
    })]
    async fn recv(&mut self, message: Message) -> Result<(), ConnActorError> {
        ensure!(self.backlog.len() < BACKLOG_LIMIT, BacklogSnafu);
        self.backlog.push(message.clone());

        let Message::Extended(id, payload) = message else {
            return Ok(());
        };

        if !self.args.self_features.extension {
            return Err(ConnActorError::Message {
                source: message::Error::SelfFeature {
                    feature: "extension",
                },
            });
        }
        if !self.args.peer_features.extension {
            return Err(ConnActorError::Message {
                source: message::Error::PeerFeature {
                    feature: "extension",
                },
            });
        }

        let message = HalfOpenMessage::Extended(self.args.conn_id.clone(), id, payload);
        self.half_open_message_send.actor_send(message).await
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
    async fn send(&mut self, id: u8, payload: Bytes) -> Result<(), ConnActorError> {
        assert!(self.args.self_features.extension && self.args.peer_features.extension);
        self.args
            .sink
            .send(Message::Extended(id, payload))
            .await
            .context(IoSnafu)
    }

    async fn shutdown(
        mut self,
        disconnected: bool,
        mut result: Result<(), ConnActorError>,
    ) -> Result<Option<(ConnArgs, Backlog)>, Error> {
        match result {
            Ok(()) if !disconnected => {} // Transfer `ConnArgs` to `Conn`.
            Err(ConnActorError::Io { .. }) => {}
            _ => result = result.and(self.args.sink.close().await.context(IoSnafu)),
        }

        let conn_id = &self.args.conn_id;
        match &result {
            Ok(()) => tracing::info!(%conn_id, "half-open peer disconnected"),
            Err(error) => tracing::warn!(%conn_id, %error, "half-open peer disconnected"),
        }

        let result = match result {
            Ok(()) => Ok(()),
            Err(error) => Err(Arc::new(error.into_broadcast()?)),
        };
        let message = HalfOpenMessage::Disconnect(self.args.conn_id.clone(), result);
        self.half_open_message_send.send(message).await?;

        if let Err(error) = self.torrent_change_guard.shutdown().await {
            tracing::warn!(%conn_id, %error, "torrent change shutdown");
        }

        Ok((!disconnected).then_some((self.args, self.backlog)))
    }
}

impl ConnActorLoop {
    async fn run(mut self) -> HalfOpenResult {
        let mut result = self.__actor.startup().await;
        if matches!(result, Ok(())) {
            result = self.run_impl().await;
        }
        self.__actor.shutdown(self.__cancel.is_set(), result).await
    }
}

impl HalfOpenConn {
    pub(super) fn spawn(
        args: ConnArgs,
        model: Arc<Mutex<Model>>,
        half_open_message_send: HalfOpenMessageSend,
    ) -> Result<(Self, HalfOpenConnGuard), ConnArgs> {
        let torrent_change;
        let torrent_change_guard;
        {
            let model = model.must_lock();
            if model.torrents().contains(args.conn_id.info_hash()) {
                return Err(args);
            }
            (torrent_change, torrent_change_guard) = model::spawn(&model, args.conn_id.info_hash());
        }
        Ok(Self::spawn_impl(
            args.self_features,
            args.peer_features,
            ConnActor {
                args,

                torrent_change,
                torrent_change_guard,

                half_open_message_send,
                backlog: Backlog::new(),
            },
        ))
    }

    pub fn self_features(&self) -> Features {
        self.self_features
    }

    pub fn peer_features(&self) -> Features {
        self.peer_features
    }
}
