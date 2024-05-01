#![feature(iterator_try_collect)]
#![feature(never_type)]
#![feature(slice_take)]

use std::io::{self, Write};
use std::marker::PhantomData;
use std::str;
use std::sync::Arc;
use std::time::Duration;

use fasthash::city;
use futures::stream::{BoxStream, TryStreamExt};
use serde::{Deserialize, Serialize};
use snafu::prelude::*;
use tokio::time;
use uuid::Uuid;

use g1_tokio::task::JoinGuard;

use etcd_client::{Client, Key, KeyValue, Value};

const TIME_TO_LIVE: Duration = Duration::from_secs(2);

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

        let lease_id = Self::lease_id(id);
        let key = self.scheme.encode(id);
        let value = Self::encode(data);
        tracing::debug!(
            lease_id,
            key = %unsafe { str::from_utf8_unchecked(&key) },
            value = %unsafe { str::from_utf8_unchecked(&value) },
        );

        self.lease(lease_id).await?;
        self.client
            .as_ref()
            .put(key.clone(), value.clone(), Some(lease_id))
            .await?;

        let mut interval = time::interval(TIME_TO_LIVE / 2);
        loop {
            interval.tick().await;

            if self.lease(lease_id).await? {
                tracing::warn!(
                    lease_id,
                    key = %unsafe { str::from_utf8_unchecked(&key) },
                    value = %unsafe { str::from_utf8_unchecked(&value) },
                    "republish lost data",
                );
                self.client
                    .as_ref()
                    .put(key.clone(), value.clone(), Some(lease_id))
                    .await?;
            }
        }
    }

    fn lease_id(id: Uuid) -> i64 {
        i64::from_be_bytes(city::hash64(id.as_bytes()).to_be_bytes())
    }

    async fn lease(&self, lease_id: i64) -> Result<bool, Error> {
        match self.client.as_ref().lease_keep_alive(lease_id).await {
            Ok(()) => Ok(false),
            Err(Error::LeaseIdNotFound { .. }) => {
                self.client
                    .as_ref()
                    .lease_grant(TIME_TO_LIVE, Some(lease_id))
                    .await?;
                Ok(true)
            }
            Err(error) => Err(error),
        }
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
        Uuid::parse_str(str::from_utf8(key.as_slice().take(self.prefix.len()..)?).ok()?).ok()
    }

    fn encode(&self, id: Uuid) -> Key {
        const UUID_LEN: usize = 16;
        let mut key = Key::with_capacity(self.prefix.len() + UUID_LEN);
        std::write!(&mut key, "{}{}", self.prefix, id).unwrap();
        key
    }
}
