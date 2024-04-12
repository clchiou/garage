use std::collections::{HashMap, VecDeque};
use std::sync::Mutex;
use std::time::Duration;

use tokio::sync::OwnedSemaphorePermit;
use tokio::time::Instant;

use g1_base::sync::MutexExt;

use ddcache_proto::Token;
use ddcache_storage::{ReadGuard, WriteGuard};

#[derive(Debug)]
pub(crate) struct State(Mutex<Inner>);

#[derive(Debug)]
struct Inner {
    map: HashMap<Token, Io>,

    // For now, we can use `VecDeque` because `timeout` is fixed.
    deadlines: VecDeque<(Instant, Token)>,
    timeout: Duration,
}

#[derive(Debug)]
pub(crate) enum Io {
    Reader(Reader),
    Writer(Writer),
}

pub(crate) type Reader = (ReadGuard, OwnedSemaphorePermit);
pub(crate) type Writer = (WriteGuard, usize, OwnedSemaphorePermit);

impl State {
    pub(crate) fn new() -> Self {
        Self(Mutex::new(Inner::new()))
    }

    pub(crate) fn next_deadline(&self) -> Option<Instant> {
        self.0
            .must_lock()
            .deadlines
            .front()
            .map(|(deadline, _)| *deadline)
    }

    pub(crate) fn remove_expired(&self, now: Instant) {
        let mut inner = self.0.must_lock();
        while let Some((deadline, token)) = inner.deadlines.front().copied() {
            if deadline <= now {
                if inner.map.remove(&token).is_some() {
                    tracing::warn!(token, "expire");
                }
                inner.deadlines.pop_front();
            } else {
                break;
            }
        }
    }

    pub(crate) fn insert_reader(&self, reader: Reader) -> Token {
        self.insert(Io::Reader(reader))
    }

    pub(crate) fn insert_writer(&self, writer: Writer) -> Token {
        self.insert(Io::Writer(writer))
    }

    fn insert(&self, io: Io) -> Token {
        let mut inner = self.0.must_lock();
        let token = inner.next_token();
        let deadline = Instant::now() + inner.timeout;
        assert!(inner.map.insert(token, io).is_none());
        inner.deadlines.push_back((deadline, token));
        token
    }

    pub(crate) fn remove(&self, token: Token) -> Option<Io> {
        self.0.must_lock().map.remove(&token)
    }
}

impl Inner {
    fn new() -> Self {
        Self {
            map: HashMap::new(),
            deadlines: VecDeque::new(),
            timeout: *crate::blob_lease_timeout(),
        }
    }

    fn next_token(&self) -> Token {
        for _ in 0..4 {
            let token = rand::random();
            // It is a small detail, but we do not generate 0.
            if token != 0 && !self.map.contains_key(&token) {
                return token;
            }
        }
        std::panic!("cannot generate random token")
    }
}
