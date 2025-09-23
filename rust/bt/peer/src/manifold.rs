use std::assert_matches::assert_matches;
use std::sync::{Arc, Mutex};

use futures::sink::SinkExt;
use tokio::task::Id;

use g1_base::collections::HashBasedBiTable;
use g1_base::sync::MutexExt;
use g1_tokio::task::{JoinGuard, JoinQueue};

use bt_base::ConnId;
use bt_model::Model;
use bt_proto::Message;

use crate::conn::{Conn, ConnGuard};
use crate::error::Error;
use crate::half_open::Backlog;
use crate::{ConnArgs, PeerMessageRecv, PeerMessageSend};

struct ManifoldActor {
    model: Arc<Mutex<Model>>,

    peer_message_send: PeerMessageSend,

    conns: Conns,
    conn_guards: JoinQueue<Result<(), Error>>,
}

pub type ManifoldGuard = JoinGuard<Result<(), Error>>;

type Conns = Arc<Mutex<HashBasedBiTable<ConnId, Id, Conn>>>;

#[g1_actor::actor(
    stub(
        pub, Manifold, struct {
            conns: Conns,
            peer_message_send: PeerMessageSend,
        },
        spawn(spawn_impl),
    ),
    loop_(
        type Result<(), Error>,
        run(run_impl),
        return Ok(()),
    ),
)]
impl ManifoldActor {
    #[actor::method(
        pub,
        stub(return { let result: bool = ConnArgs::convert_connect_result(result).await; }),
    )]
    async fn connect(&self, args: ConnArgs) -> bool {
        self.with_backlog(args, Backlog::new()).await
    }

    #[actor::method(
        pub(crate),
        stub(return { let result: bool = ConnArgs::convert_with_backlog_result(result).await; }),
    )]
    async fn with_backlog(&self, args: ConnArgs, backlog: Backlog) -> bool {
        match self.spawn_conn(args, backlog) {
            Ok(()) => true,
            Err(ConnArgs {
                conn_id, mut sink, ..
            }) => {
                if let Err(error) = sink.close().await {
                    tracing::warn!(%conn_id, %error, "torrent removed; close conn");
                }
                false
            }
        }
    }

    fn spawn_conn(&self, args: ConnArgs, backlog: Backlog) -> Result<(), ConnArgs> {
        let mut conns = self.conns.must_lock();
        assert!(
            !conns.contains_row(&args.conn_id),
            "peer conn id collide: {}",
            args.conn_id,
        );

        let conn_id = args.conn_id.clone();
        let (conn, guard) = Conn::spawn(
            args,
            backlog,
            self.model.clone(),
            self.peer_message_send.clone(),
        )?;

        assert_matches!(conns.insert(conn_id, guard.id(), conn), Err((None, None)));
        self.conn_guards.push(guard).expect("conn_guards");
        Ok(())
    }

    #[actor::loop_(react = {
        let guard = self.conn_guards.join_next();
        self.join_conn(guard.expect("guard"))?;
    })]
    fn join_conn(&self, mut guard: ConnGuard) -> Result<(), Error> {
        let (conn_id, _) = self
            .conns
            .must_lock()
            .remove_column(&guard.id())
            .expect("conn");

        match guard.take_result() {
            Ok(result) => result,
            Err(error) => {
                // Right now, we return `Ok`.  Should we return `Err` instead?  If so, what kind?
                tracing::warn!(%conn_id, %error, "peer shutdown");
                Ok(())
            }
        }
    }

    async fn shutdown(&self) -> Result<(), Error> {
        self.conns.must_lock().clear();

        match self.conn_guards.shutdown().await {
            Ok(result) => result,
            Err(error) => {
                // Right now, we return `Ok`.  Should we return `Err` instead?  If so, what kind?
                tracing::warn!(%error, "peer shutdown");
                Ok(())
            }
        }
    }
}

impl ManifoldActorLoop {
    async fn run(&mut self) -> Result<(), Error> {
        let result = self.run_impl().await;
        result.and(self.__actor.shutdown().await)
    }
}

impl Manifold {
    pub fn spawn(model: Arc<Mutex<Model>>) -> (Self, ManifoldGuard) {
        let peer_message_send = PeerMessageSend::new();
        let conns = Arc::new(Mutex::new(HashBasedBiTable::new()));
        let actor = ManifoldActor {
            model,
            peer_message_send: peer_message_send.clone(),
            conns: conns.clone(),
            conn_guards: JoinQueue::new(),
        };
        Self::spawn_impl(conns, peer_message_send, actor)
    }

    pub fn get(&self, conn_id: &ConnId) -> Option<Conn> {
        self.conns
            .must_lock()
            .get_row(conn_id)
            .map(|(_, conn)| conn.clone())
    }

    pub async fn send(&self, conn_id: &ConnId, message: Message) {
        if let Some(conn) = self.get(conn_id) {
            conn.send(message).await;
        }
    }

    pub fn subscribe(&self) -> PeerMessageRecv {
        self.peer_message_send.subscribe()
    }
}
