use std::cmp::{Ordering, Reverse};
use std::collections::BinaryHeap;
use std::net::SocketAddr;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tokio::sync::Notify;
use tokio::time::{self, Instant};

use g1_base::sync::MutexExt;
use g1_tokio::task::JoinGuard;

use bt_dht_proto::Token;

const TIMEOUT: Duration = Duration::from_mins(10);

struct IssuerActor {
    tokens: Arc<Tokens>,
}

pub(crate) type IssuerGuard = JoinGuard<()>;

#[derive(Debug)]
struct Tokens {
    // TODO: This is not very efficient, but it should be good enough for now.
    tokens: Mutex<BinaryHeap<Reverse<Issued>>>,
    changed: Notify,
}

#[derive(Debug)]
struct Issued {
    node_endpoint: SocketAddr,
    token: Token,
    expire_at: Instant,
}

#[g1_actor::actor(
    stub(
        pub(crate), Issuer, struct {
            tokens: Arc<Tokens>,
        },
        spawn(spawn_impl),
    ),
    loop_(react = { let () = self.tokens.changed(); }),
)]
impl IssuerActor {
    #[actor::loop_(react = {
        let Some(()) = self.wait_expire();
        self.expire()
    })]
    async fn wait_expire(&self) -> Option<()> {
        let expire_at = self.tokens.next_expire_at()?;
        time::sleep_until(expire_at).await;
        Some(())
    }

    fn expire(&self) {
        self.tokens.expire()
    }
}

impl Issuer {
    pub(crate) fn spawn() -> (Self, IssuerGuard) {
        let tokens = Arc::new(Tokens::new());
        Self::spawn_impl(tokens.clone(), IssuerActor { tokens })
    }

    pub(crate) fn issue(&self, node: SocketAddr) -> Token {
        self.tokens.issue(node)
    }

    pub(crate) fn verify(&self, node: SocketAddr, token: Token) -> bool {
        self.tokens.verify(node, token)
    }
}

impl Tokens {
    fn new() -> Self {
        Self {
            tokens: Mutex::new(BinaryHeap::new()),
            changed: Notify::new(),
        }
    }

    fn next_expire_at(&self) -> Option<Instant> {
        self.tokens
            .must_lock()
            .peek()
            .map(|Reverse(issued)| issued.expire_at)
    }

    fn expire(&self) {
        let mut tokens = self.tokens.must_lock();
        let mut changed = false;
        while let Some(Reverse(issued)) = tokens.peek() {
            if issued.is_expired() {
                tokens.pop();
                changed = true;
            } else {
                break;
            }
        }
        if changed {
            self.changed.notify_waiters();
        }
    }

    fn issue(&self, node_endpoint: SocketAddr) -> Token {
        let issued = Issued::issue(node_endpoint);
        let token = issued.token.clone();
        self.tokens.must_lock().push(Reverse(issued));
        self.changed.notify_waiters();
        token
    }

    fn verify(&self, node_endpoint: SocketAddr, token: Token) -> bool {
        self.tokens
            .must_lock()
            .as_slice()
            .iter()
            .any(|Reverse(issued)| issued.verify(node_endpoint, &token))
    }

    async fn changed(&self) {
        self.changed.notified().await
    }
}

impl Issued {
    fn issue(node_endpoint: SocketAddr) -> Self {
        Self {
            node_endpoint,
            // Unlike the BitTorrent implementation, we use purely random values for tokens.
            token: Token::copy_from_slice(&rand::random::<[u8; 4]>()),
            expire_at: Instant::now() + TIMEOUT,
        }
    }

    fn is_expired(&self) -> bool {
        !self.expire_at.elapsed().is_zero()
    }

    fn verify(&self, node_endpoint: SocketAddr, token: &Token) -> bool {
        self.node_endpoint == node_endpoint && self.token == token && !self.is_expired()
    }
}

impl PartialEq for Issued {
    fn eq(&self, other: &Self) -> bool {
        self.expire_at == other.expire_at
    }
}

impl Eq for Issued {}

impl PartialOrd for Issued {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for Issued {
    fn cmp(&self, other: &Self) -> Ordering {
        self.expire_at.cmp(&other.expire_at)
    }
}
