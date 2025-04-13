//! Helper for watching a key or a key range.

use std::ops::{Bound, RangeBounds};

use crate::{Client, Error, Event, Key, KeyValue, TryBoxStream};

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Watch {
    Range(Bound<Key>, Bound<Key>),
    Prefix(Key),
    Key(Key),
}

impl Watch {
    pub fn range<K>(range: impl RangeBounds<K>) -> Self
    where
        K: AsRef<[u8]>,
    {
        fn to_vec(key: impl AsRef<[u8]>) -> Key {
            key.as_ref().to_vec()
        }

        Self::Range(
            range.start_bound().map(to_vec),
            range.end_bound().map(to_vec),
        )
    }

    pub fn prefix<K>(key: K) -> Self
    where
        K: Into<Key>,
    {
        Self::Prefix(key.into())
    }

    pub fn key<K>(key: K) -> Self
    where
        K: Into<Key>,
    {
        Self::Key(key.into())
    }

    pub async fn scan_from(
        &self,
        client: &Client,
        limit: Option<i64>,
    ) -> Result<Vec<KeyValue>, Error> {
        match self {
            Self::Range(start, end) => client.range::<&Key>(range((start, end)), limit).await,
            Self::Prefix(key) => client.range_prefix(key.clone(), limit).await,
            Self::Key(key) => client
                .get(key.clone())
                .await
                .map(|value| value.map_or_else(Vec::new, |value| vec![(key.clone(), value)])),
        }
    }

    pub async fn watch_from(&self, client: &Client) -> Result<TryBoxStream<Event>, Error> {
        match self {
            Self::Range(start, end) => client.watch::<&Key>(range((start, end))).await,
            Self::Prefix(key) => client.watch_prefix(key.clone()).await,
            Self::Key(key) => client.watch_key(key.clone()).await,
        }
    }
}

fn range<'a>((start, end): (&'a Bound<Key>, &'a Bound<Key>)) -> (Bound<&'a Key>, Bound<&'a Key>) {
    (start.as_ref(), end.as_ref())
}
