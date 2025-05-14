#![feature(duration_constants)]
#![feature(iterator_try_collect)]
#![feature(never_type)]
#![feature(try_blocks)]

use std::io::{self, Write};
use std::marker::PhantomData;
use std::str;
use std::sync::Arc;
use std::time::{Duration, Instant};

use fasthash::city;
use futures::stream::{BoxStream, TryStreamExt};
use reqwest::StatusCode;
use serde::{Deserialize, Serialize};
use snafu::prelude::*;
use tokio::time;
use uuid::Uuid;

use g1_tokio::task::JoinGuard;

use etcd_client::{Client, Key, KeyValue, Value};

// TODO: Pick a sensible default value.
g1_param::define!(
    time_to_live: Duration = Duration::from_secs(10);
    parse = g1_param::parse::duration;
);

pub use etcd_client::Error;

#[derive(Debug, Snafu)]
pub enum SubscriberError {
    #[snafu(display("decode error: {source}"))]
    Decode { source: serde_json::Error },
    #[snafu(display("parse id error: {key:?}"))]
    ParseId { key: Key },
    #[snafu(display("request error: {source}"))]
    Request { source: Error },
}

#[derive(Clone, Debug)]
pub struct PubSub<T, C = Client> {
    client: C,
    scheme: KeyScheme,
    time_to_live: Duration,
    _data: PhantomData<T>,
}

#[derive(Clone, Debug)]
struct KeyScheme {
    prefix: Arc<str>,
}

// It is a bit friendlier to return `io::Error` than `etcd_client::Error`.
pub type PublisherGuard = JoinGuard<Result<(), io::Error>>;

// TODO: For reasons that are still unknown to me, if the stream were not wrapped in `BoxStream`,
// it would not implement `Unpin` and would be virtually unusable.
pub type Subscriber<T> = BoxStream<'static, Result<Event<T>, SubscriberError>>;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Event<T> {
    Create(Item<T>),
    Update { id: Uuid, new: T, old: T },
    Delete(Item<T>),
}

pub type Item<T> = (Uuid, T);

impl<T> PubSub<T, Client>
where
    T: for<'a> Deserialize<'a> + Serialize,
{
    pub fn new(prefix: String) -> Self {
        Self::with_client(prefix, Client::new())
    }
}

impl<T, C> PubSub<T, C>
where
    T: for<'a> Deserialize<'a> + Serialize,
    C: AsRef<Client> + Send + Sync + 'static,
{
    pub fn with_client(prefix: String, client: C) -> Self {
        Self {
            client,
            scheme: KeyScheme::new(prefix),
            time_to_live: *time_to_live(),
            _data: PhantomData,
        }
    }

    fn decode(value: Value) -> Result<T, SubscriberError> {
        serde_json::from_slice::<T>(&value).context(DecodeSnafu)
    }

    fn encode(data: &T) -> Value {
        serde_json::to_vec(data).unwrap()
    }

    //
    // Publisher
    //

    pub fn spawn(self, id: Uuid, data: T) -> PublisherGuard
    where
        T: Send + Sync + 'static,
    {
        PublisherGuard::spawn(move |cancel| async move {
            tokio::select! {
                () = cancel.wait() => Ok(()),
                result = self.publish(id, &data) => Err(io::Error::other(result.unwrap_err())),
            }
        })
    }

    pub async fn publish(&self, id: Uuid, data: &T) -> Result<!, Error> {
        tracing::info!(prefix = %self.scheme.prefix, %id, "publish");

        let key = self.scheme.encode(id);
        let lease_id = Self::lease_id(&key);
        let value = Self::encode(data);
        tracing::debug!(
            lease_id,
            key = %unsafe { str::from_utf8_unchecked(&key) },
            value = %unsafe { str::from_utf8_unchecked(&value) },
        );

        #[derive(Debug)]
        enum Action {
            LeaseGrant,
            Publish,
            LeaseKeepAlive,
        }

        // I observed that our etcd cluster is quite unstable, likely due to running on hardware
        // that falls below the recommended specifications.  To mitigate this issue, we will retry
        // requests for a longer period.
        const TIMEOUT: Duration = Duration::from_secs(10);

        let mut action = Action::LeaseGrant;
        let mut retry_start_at: Option<Instant> = None;
        loop {
            let result = try {
                match action {
                    Action::LeaseGrant => {
                        self.client
                            .as_ref()
                            .lease_grant(self.time_to_live, Some(lease_id))
                            .await?;
                        Action::Publish
                    }
                    Action::Publish => {
                        self.client
                            .as_ref()
                            .put(key.clone(), value.clone(), Some(lease_id))
                            .await?;
                        Action::LeaseKeepAlive
                    }
                    Action::LeaseKeepAlive => {
                        self.client.as_ref().lease_keep_alive(lease_id).await?;
                        time::sleep(self.time_to_live / 2).await;
                        Action::LeaseKeepAlive
                    }
                }
            };
            match (&action, result) {
                (_, Ok(next_action)) => {
                    action = next_action;
                    retry_start_at = None;
                }

                // Lease likely already exists.
                (Action::LeaseGrant, Err(Error::Grpc { status: StatusCode::BAD_REQUEST })) => {
                    action = Action::Publish;
                    retry_start_at = None;
                }

                (_, Err(Error::LeaseIdNotFound { .. })) => {
                    tracing::warn!(
                        lease_id,
                        key = %unsafe { str::from_utf8_unchecked(&key) },
                        value = %unsafe { str::from_utf8_unchecked(&value) },
                        "unexpected lease expire",
                    );
                    action = Action::LeaseGrant;
                    retry_start_at = None;
                }

                // These errors are usually the result of the etcd cluster being too busy:
                // * It is too busy to process our authentication request.
                (_, Err(error @ Error::Grpc { status: StatusCode::UNAUTHORIZED }))
                // * Our lease has expired by the time it is finally able to process our request.
                | (_, Err(error @ Error::Grpc { status: StatusCode::NOT_FOUND }))
                | (_, Err(error @ Error::Grpc { status: StatusCode::SERVICE_UNAVAILABLE })) => {
                    if retry_start_at.is_some_and(|x| x.elapsed() > TIMEOUT) {
                        tracing::warn!("retry timeout");
                        return Err(error);
                    }

                    tracing::warn!(?action, %error, "retry due to etcd too busy");
                    action = Action::LeaseGrant;

                    // We use a constant backoff for now.
                    time::sleep(Duration::SECOND).await;
                    retry_start_at.get_or_insert_with(Instant::now);
                }

                (_, Err(error)) => return Err(error),
            }
        }
    }

    fn lease_id(key: &[u8]) -> i64 {
        i64::from_be_bytes(city::hash64(key).to_be_bytes())
    }

    //
    // Subscriber
    //

    pub async fn scan(&self) -> Result<Vec<Item<T>>, SubscriberError> {
        let scheme = self.scheme.clone();
        self.client
            .as_ref()
            .range_prefix(self.scheme.prefix.as_bytes(), None)
            .await
            .context(RequestSnafu)?
            .into_iter()
            .map(move |kv| Self::decode_kv(&scheme, kv))
            .try_collect()
    }

    pub async fn subscribe(&self) -> Result<Subscriber<T>, SubscriberError> {
        let scheme = self.scheme.clone();
        Ok(Box::pin(
            self.client
                .as_ref()
                .watch_prefix(self.scheme.prefix.as_bytes())
                .await
                .context(RequestSnafu)?
                .map_err(|source| SubscriberError::Request { source })
                .and_then(move |event| {
                    let scheme = scheme.clone();
                    async move { Self::decode_event(&scheme, event) }
                }),
        ))
    }

    fn decode_event(
        scheme: &KeyScheme,
        event: etcd_client::Event,
    ) -> Result<Event<T>, SubscriberError> {
        Ok(match event {
            etcd_client::Event::Create(kv) => Event::Create(Self::decode_kv(scheme, kv)?),
            etcd_client::Event::Update { key, new, old } => Event::Update {
                id: scheme.decode(key)?,
                new: Self::decode(new)?,
                old: Self::decode(old)?,
            },
            etcd_client::Event::Delete(kv) => Event::Delete(Self::decode_kv(scheme, kv)?),
        })
    }

    fn decode_kv(scheme: &KeyScheme, (key, value): KeyValue) -> Result<Item<T>, SubscriberError> {
        Ok((scheme.decode(key)?, Self::decode(value)?))
    }
}

impl KeyScheme {
    fn new(prefix: String) -> Self {
        Self {
            prefix: prefix.into(),
        }
    }

    fn decode(&self, key: Key) -> Result<Uuid, SubscriberError> {
        self.parse(&key).context(ParseIdSnafu { key })
    }

    fn parse(&self, key: &Key) -> Option<Uuid> {
        Uuid::parse_str(str::from_utf8(key.as_slice().split_off(self.prefix.len()..)?).ok()?).ok()
    }

    fn encode(&self, id: Uuid) -> Key {
        const UUID_LEN: usize = 16;
        let mut key = Key::with_capacity(self.prefix.len() + UUID_LEN);
        std::write!(&mut key, "{}{}", self.prefix, id).unwrap();
        key
    }
}
