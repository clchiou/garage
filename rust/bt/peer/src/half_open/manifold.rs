use std::assert_matches::assert_matches;
use std::sync::{Arc, Mutex};

use bytes::Bytes;
use tokio::task::Id;

use g1_base::collections::HashBasedBiTable;
use g1_base::sync::MutexExt;
use g1_tokio::task::{JoinGuard, JoinQueue};

use bt_base::ConnId;
use bt_model::Model;

use crate::ConnArgs;
use crate::error::Error;
use crate::manifold::Manifold;

use super::conn::{HalfOpenConn, HalfOpenConnGuard, HalfOpenResult};
use super::{HalfOpenMessageRecv, HalfOpenMessageSend};

struct ManifoldActor {
    model: Arc<Mutex<Model>>,

    half_open_message_send: HalfOpenMessageSend,

    conns: Conns,
    conn_guards: JoinQueue<HalfOpenResult>,

    manifold: Manifold,
}

pub type HalfOpenManifoldGuard = JoinGuard<Result<(), Error>>;

type Conns = Arc<Mutex<HashBasedBiTable<ConnId, Id, HalfOpenConn>>>;

#[g1_actor::actor(
    stub(
        pub, HalfOpenManifold, struct {
            conns: Conns,
            half_open_message_send: HalfOpenMessageSend,
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
        match self.spawn_conn(args) {
            Ok(()) => true,
            Err(args) => self.manifold.connect(args).await,
        }
    }

    fn spawn_conn(&self, args: ConnArgs) -> Result<(), ConnArgs> {
        let mut conns = self.conns.must_lock();
        assert!(
            !conns.contains_row(&args.conn_id),
            "half-open peer conn id collide: {}",
            args.conn_id,
        );

        let conn_id = args.conn_id.clone();
        let (conn, guard) = HalfOpenConn::spawn(
            args,
            self.model.clone(),
            self.half_open_message_send.clone(),
        )?;

        assert_matches!(conns.insert(conn_id, guard.id(), conn), Err((None, None)));
        self.conn_guards.push(guard).expect("conn_guards");
        Ok(())
    }

    #[actor::loop_(react = {
        let guard = self.conn_guards.join_next();
        self.join_conn(guard.expect("guard")).await?;
    })]
    async fn join_conn(&self, mut guard: HalfOpenConnGuard) -> Result<(), Error> {
        let (conn_id, _) = self
            .conns
            .must_lock()
            .remove_column(&guard.id())
            .expect("conn");

        match guard.take_result() {
            Ok(result) => {
                if let Some((args, backlog)) = result? {
                    self.manifold.with_backlog(args, backlog).await;
                }
                Ok(())
            }
            Err(error) => {
                // Right now, we return `Ok`.  Should we return `Err` instead?  If so, what kind?
                tracing::warn!(%conn_id, %error, "half-open peer shutdown");
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
                tracing::warn!(%error, "half-open peer shutdown");
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

impl HalfOpenManifold {
    pub fn spawn(model: Arc<Mutex<Model>>, manifold: Manifold) -> (Self, HalfOpenManifoldGuard) {
        let half_open_message_send = HalfOpenMessageSend::new();
        let conns = Arc::new(Mutex::new(HashBasedBiTable::new()));
        let actor = ManifoldActor {
            model,
            half_open_message_send: half_open_message_send.clone(),
            conns: conns.clone(),
            conn_guards: JoinQueue::new(),
            manifold,
        };
        Self::spawn_impl(conns, half_open_message_send, actor)
    }

    pub fn get(&self, conn_id: &ConnId) -> Option<HalfOpenConn> {
        self.conns
            .must_lock()
            .get_row(conn_id)
            .map(|(_, conn)| conn.clone())
    }

    pub async fn send(&self, conn_id: &ConnId, id: u8, payload: Bytes) {
        if let Some(conn) = self.get(conn_id) {
            conn.send(id, payload).await;
        }
    }

    pub fn subscribe(&self) -> HalfOpenMessageRecv {
        self.half_open_message_send.subscribe()
    }
}
