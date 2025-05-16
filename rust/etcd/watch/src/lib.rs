use std::io;
use std::sync::Arc;
use std::time::Duration;

use futures::stream::StreamExt;
use tokio::sync::broadcast::{self, Receiver, Sender, WeakSender};
use tokio::time;

use g1_tokio::task::{Cancel, JoinGuard};

use etcd_client::watch::Watch;
use etcd_client::{Client, Error, Event, KeyValue, TryBoxStream};

#[derive(Debug)]
pub struct WatcherSpawner {
    event_send: WatcherEventSend,
}

// Exposes an etcd watch through a tokio broadcast channel.
#[derive(Clone, Debug)]
pub struct Watcher {
    subscriber: WatcherEventSubscriber,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum WatcherEvent {
    Init(Vec<KeyValue>),
    Event(Event),
}

pub type WatcherEventRecv = Receiver<WatcherEvent>;
type WatcherEventSend = Sender<WatcherEvent>;
type WatcherEventSubscriber = WeakSender<WatcherEvent>;

// For convenience, we return `io::Error` instead of `etcd_client::Error`.
pub type WatcherGuard = JoinGuard<Result<(), io::Error>>;

#[derive(Debug)]
struct Actor {
    cancel: Cancel,
    client: Arc<Client>,
    watch: Watch,
    event_send: WatcherEventSend,
}

impl Default for WatcherSpawner {
    fn default() -> Self {
        Self::new()
    }
}

impl WatcherSpawner {
    pub fn new() -> Self {
        let (event_send, _) = broadcast::channel(16);
        Self { event_send }
    }

    pub fn subscribe(&self) -> WatcherEventRecv {
        self.event_send.subscribe()
    }

    pub fn spawn(self, client: Arc<Client>, watch: Watch) -> (Watcher, WatcherGuard) {
        let Self { event_send } = self;
        let subscriber = event_send.downgrade();
        (
            Watcher::new(subscriber),
            WatcherGuard::spawn(move |cancel| Actor::new(cancel, client, watch, event_send).run()),
        )
    }
}

impl Watcher {
    fn new(subscriber: WatcherEventSubscriber) -> Self {
        Self { subscriber }
    }

    pub fn subscribe(&self) -> Option<WatcherEventRecv> {
        self.subscriber.upgrade().map(|sender| sender.subscribe())
    }
}

type StreamInit = (TryBoxStream<Event>, Vec<KeyValue>);

impl Actor {
    fn new(
        cancel: Cancel,
        client: Arc<Client>,
        watch: Watch,
        event_send: WatcherEventSend,
    ) -> Self {
        Self {
            cancel,
            client,
            watch,
            event_send,
        }
    }

    async fn run(self) -> Result<(), io::Error> {
        tokio::select! {
            () = self.cancel.wait() => Ok(()),
            result = self.watch() => result.map_err(io::Error::other),
        }
    }

    async fn watch(&self) -> Result<(), Error> {
        let mut stream_container: Option<TryBoxStream<Event>> = None;
        loop {
            let event = match stream_container.as_mut() {
                Some(stream) => match stream.next().await {
                    Some(Ok(event)) => WatcherEvent::Event(event),
                    Some(Err(error)) => {
                        tracing::warn!(%error, "watcher");
                        stream_container = None;
                        continue;
                    }
                    None => {
                        tracing::warn!("watcher stop unexpectedly");
                        stream_container = None;
                        continue;
                    }
                },
                None => {
                    let (stream, init) = self.init().await?;
                    stream_container = Some(stream);
                    WatcherEvent::Init(init)
                }
            };
            if self.event_send.send(event).is_err() {
                tracing::debug!("all watcher receiver dropped; exit");
                break;
            }
        }
        Ok(())
    }

    async fn init(&self) -> Result<StreamInit, Error> {
        const NUM_RETRIES: usize = 4;
        let mut backoff = Duration::from_secs(1);
        for retry in 0..NUM_RETRIES {
            match self.try_init().await {
                Ok(stream_init) => return Ok(stream_init),
                Err(error) => {
                    tracing::warn!(retry, %error, "init");
                    time::sleep(backoff).await;
                    backoff *= 2;
                }
            }
        }
        self.try_init().await
    }

    async fn try_init(&self) -> Result<StreamInit, Error> {
        // It is important that the stream be created before the initial scan.
        let stream = self.watch.watch_from(&self.client).await?;
        let init = self.watch.scan_from(&self.client, None).await?;
        Ok((stream, init))
    }
}
