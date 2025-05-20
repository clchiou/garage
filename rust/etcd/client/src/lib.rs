//! Rudimentary etcd client.

pub mod request;
pub mod response;
pub mod watch;

mod private;

use std::io;
use std::ops::{Bound, RangeBounds};
use std::str;
use std::sync::Mutex;
use std::time::Duration;

use futures::io::AsyncBufReadExt;
use futures::stream::{self, BoxStream, Stream, TryStreamExt};
use reqwest::header::{HeaderName, HeaderValue, AUTHORIZATION};
use reqwest::{Response, StatusCode, Url};
use serde::Deserialize;
use snafu::prelude::*;

use g1_base::sync::MutexExt;
use g1_url::UrlExt;

use crate::private::{Request, StreamRequest};
use crate::response::Status;

g1_param::define!(endpoint: Url = "http://127.0.0.1:2379".parse().unwrap());
g1_param::define!(auth: Option<Auth> = None);

#[derive(Debug, Snafu)]
pub enum Error {
    #[snafu(display("response decode error: {source}"))]
    Decode { source: serde_json::Error },
    #[snafu(display("grpc error: {status}"))]
    Grpc { status: StatusCode },
    #[snafu(display("http error: {source} status={:?}", source.status()))]
    Http { source: reqwest::Error },
    #[snafu(display("invalid token: {token:?}"))]
    InvalidToken { token: String },
    #[snafu(display("invalid watch delete event: {event:?}"))]
    InvalidWatchDelete {
        // Box it to prevent `clippy::result_large_err`.
        event: Box<response::Event>,
    },
    #[snafu(display("lease grant: {error}"))]
    LeaseGrant { error: String },
    #[snafu(display("lease id not found: {id}"))]
    LeaseIdNotFound { id: i64 },
    #[snafu(display("stream error: {status:?}"))]
    Stream { status: Status },
}

#[derive(Debug)]
pub struct Client {
    client: reqwest::Client,
    endpoint: Url,
    auth: Option<Auth>,
    auth_header: Mutex<Option<HeaderValue>>,
}

#[derive(Debug)]
pub struct ClientBuilder {
    endpoint: Url,
    auth: Option<Auth>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "snake_case")]
pub enum Auth {
    Authenticate(request::Authenticate),
    Authorize(String),
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Event {
    Create(KeyValue),
    Update { key: Key, new: Value, old: Value },
    Delete(KeyValue),
}

pub type KeyValue = (Key, Value);
pub type Key = Vec<u8>;
pub type Value = Vec<u8>;

// TODO: We avoid the "return impl trait" syntax to work around the issue that, currently, Rust
// implicitly captures all input lifetimes.
//
// [issue]: https://github.com/rust-lang/rust/issues/82171
pub type TryBoxStream<T> = BoxStream<'static, Result<T, Error>>;

impl Default for ClientBuilder {
    fn default() -> Self {
        Self::new()
    }
}

impl ClientBuilder {
    pub fn new() -> Self {
        Self {
            endpoint: endpoint().clone().ensure_trailing_slash(),
            auth: auth().clone(),
        }
    }

    pub fn endpoint(mut self, endpoint: Url) -> Self {
        self.endpoint = endpoint.ensure_trailing_slash();
        self
    }

    pub fn auth(mut self, auth: Option<Auth>) -> Self {
        self.auth = auth;
        self
    }

    pub fn build(self) -> Client {
        Client {
            client: reqwest::Client::new(),
            endpoint: self.endpoint,
            auth: self.auth,
            auth_header: Mutex::new(None),
        }
    }
}

impl Default for Client {
    fn default() -> Self {
        Self::new()
    }
}

impl AsRef<Client> for Client {
    fn as_ref(&self) -> &Client {
        self
    }
}

macro_rules! rpc {
    ($self:ident, $rpc:expr $(,)?) => {{
        let mut result = $rpc;
        if let Err(Error::Grpc { status }) = &result {
            if status == &StatusCode::UNAUTHORIZED {
                match $self.force_authenticate().await {
                    Ok(true) => {
                        tracing::debug!("reauthenticate then retry");
                        result = $rpc;
                    }
                    Ok(false) => tracing::debug!("cannot reauthenticate"),
                    Err(error) => tracing::warn!(%error, "reauthenticate"),
                }
            } else if status.as_u16() >= 500 { // For now, we blindly retry on 5xx.
                tracing::warn!(%status, "retry");
                result = $rpc;
            }
        }
        result
    }};
}

impl Client {
    pub fn new() -> Self {
        ClientBuilder::new().build()
    }

    pub async fn authenticate(&self) -> Result<(), Error> {
        if !(self.auth.is_some() && self.auth_header.must_lock().is_none()) {
            return Ok(());
        }
        let auth_header = match self.auth.as_ref().unwrap() {
            Auth::Authenticate(request) => {
                to_auth_header(&self.request_with_headers(request, []).await?.token)?
            }
            Auth::Authorize(token) => to_auth_header(token)?,
        };
        *self.auth_header.must_lock() = Some(auth_header);
        Ok(())
    }

    async fn force_authenticate(&self) -> Result<bool, Error> {
        let Some(Auth::Authenticate(request)) = self.auth.as_ref() else {
            return Ok(false);
        };
        let auth_header = to_auth_header(&self.request_with_headers(request, []).await?.token)?;
        *self.auth_header.must_lock() = Some(auth_header);
        Ok(true)
    }

    pub fn auth_token(&self) -> Option<String> {
        self.auth_header
            .must_lock()
            .as_ref()
            .map(|auth_header| auth_header.to_str().unwrap().to_string())
    }

    fn headers(&self) -> impl IntoIterator<Item = (HeaderName, HeaderValue)> + use<> {
        self.auth_header
            .must_lock()
            .clone()
            .map(|auth_header| (AUTHORIZATION, auth_header))
    }

    pub async fn request<R>(&self, request: &R) -> Result<R::Response, Error>
    where
        R: Request,
    {
        self.authenticate().await?;
        rpc!(
            self,
            self.request_with_headers(request, self.headers()).await,
        )
    }

    async fn request_with_headers<R, H>(
        &self,
        request: &R,
        headers: H,
    ) -> Result<R::Response, Error>
    where
        R: Request,
        H: IntoIterator<Item = (HeaderName, HeaderValue)>,
    {
        let response = self
            .send(request, headers)
            .await?
            .bytes()
            .await
            .context(HttpSnafu)?;
        tracing::debug!(response = %response.escape_ascii());
        R::decode(&response)
    }

    pub async fn stream<R>(&self, request: &R) -> Result<TryBoxStream<R::Response>, Error>
    where
        R: StreamRequest,
    {
        self.authenticate().await?;

        let reader = rpc!(self, self.send(request, self.headers()).await)?
            .bytes_stream()
            .map_err(io::Error::other)
            .into_async_read();

        Ok(Box::pin(stream::try_unfold(
            reader,
            |mut reader| async move {
                let mut response = Vec::new();
                let size = reader
                    .read_until(b'\n', &mut response)
                    .await
                    .map_err(|error| error.downcast::<Error>().expect("downcast"))?;
                if size == 0 {
                    return Ok(None);
                }
                tracing::debug!(response = %response.escape_ascii(), "stream");
                Ok(Some((R::stream_decode(&response)?, reader)))
            },
        )))
    }

    async fn send<R, H>(&self, request: &R, headers: H) -> Result<Response, Error>
    where
        R: Request,
        H: IntoIterator<Item = (HeaderName, HeaderValue)>,
    {
        let endpoint = self.endpoint.join(R::ENDPOINT).unwrap();
        let request = request.encode();
        tracing::debug!(%endpoint, request = %unsafe { str::from_utf8_unchecked(&request) });

        let mut request = self.client.post(endpoint).body(request);
        for (name, value) in headers {
            request = request.header(name, value);
        }

        let response = request.send().await.context(HttpSnafu)?;

        // We currently treat all non-200 status codes as errors.
        let status = response.status();
        ensure!(status == StatusCode::OK, GrpcSnafu { status });

        Ok(response)
    }

    //
    // Helpers.
    //

    pub async fn range<K>(
        &self,
        range: impl RangeBounds<K>,
        limit: Option<i64>,
    ) -> Result<Vec<KeyValue>, Error>
    where
        K: AsRef<[u8]>,
    {
        let (key, range_end) = to_key_pair(range);
        Ok(to_kvs(
            self.request(&request::Range {
                key,
                range_end,
                limit: limit.unwrap_or(0),
                sort_order: request::SortOrder::ASCEND,
                sort_target: request::SortTarget::KEY,
                ..Default::default()
            })
            .await?,
        ))
    }

    pub async fn range_prefix<K>(&self, key: K, limit: Option<i64>) -> Result<Vec<KeyValue>, Error>
    where
        K: Into<Key>,
    {
        let key = key.into();
        let range_end = key_plus_one(key.clone());
        Ok(to_kvs(
            self.request(&request::Range {
                key,
                range_end,
                limit: limit.unwrap_or(0),
                sort_order: request::SortOrder::ASCEND,
                sort_target: request::SortTarget::KEY,
                ..Default::default()
            })
            .await?,
        ))
    }

    pub async fn get<K>(&self, key: K) -> Result<Option<Value>, Error>
    where
        K: Into<Key>,
    {
        Ok(self
            .request(&request::Range {
                key: key.into(),
                ..Default::default()
            })
            .await?
            .kvs
            .into_iter()
            .next()
            .map(|kv| kv.value))
    }

    pub async fn put<K, V>(
        &self,
        key: K,
        value: V,
        lease: Option<i64>,
    ) -> Result<Option<KeyValue>, Error>
    where
        K: Into<Key>,
        V: Into<Value>,
    {
        Ok(self
            .request(&request::Put {
                key: key.into(),
                value: value.into(),
                lease: lease.unwrap_or(0),
                prev_kv: true,
                ..Default::default()
            })
            .await?
            .prev_kv
            .map(|kv| (kv.key, kv.value)))
    }

    pub async fn delete<K>(&self, range: impl RangeBounds<K>) -> Result<i64, Error>
    where
        K: AsRef<[u8]>,
    {
        let (key, range_end) = to_key_pair(range);
        Ok(self
            .request(&request::DeleteRange {
                key,
                range_end,
                ..Default::default()
            })
            .await?
            .deleted)
    }

    pub async fn delete_prefix<K>(&self, key: K) -> Result<i64, Error>
    where
        K: Into<Key>,
    {
        let key = key.into();
        let range_end = key_plus_one(key.clone());
        Ok(self
            .request(&request::DeleteRange {
                key,
                range_end,
                ..Default::default()
            })
            .await?
            .deleted)
    }

    pub async fn delete_key<K>(&self, key: K) -> Result<Option<KeyValue>, Error>
    where
        K: Into<Key>,
    {
        Ok(self
            .request(&request::DeleteRange {
                key: key.into(),
                prev_kv: true,
                ..Default::default()
            })
            .await?
            .prev_kvs
            .into_iter()
            .next()
            .map(|kv| (kv.key, kv.value)))
    }

    pub async fn watch<K>(&self, range: impl RangeBounds<K>) -> Result<TryBoxStream<Event>, Error>
    where
        K: AsRef<[u8]>,
    {
        let (key, range_end) = to_key_pair(range);
        Ok(to_events(
            self.stream(&request::Watch::Create(request::WatchCreate {
                key,
                range_end,
                prev_kv: true,
                ..Default::default()
            }))
            .await?,
        ))
    }

    pub async fn watch_prefix<K>(&self, key: K) -> Result<TryBoxStream<Event>, Error>
    where
        K: Into<Key>,
    {
        let key = key.into();
        let range_end = key_plus_one(key.clone());
        Ok(to_events(
            self.stream(&request::Watch::Create(request::WatchCreate {
                key,
                range_end,
                prev_kv: true,
                ..Default::default()
            }))
            .await?,
        ))
    }

    pub async fn watch_key<K>(&self, key: K) -> Result<TryBoxStream<Event>, Error>
    where
        K: Into<Key>,
    {
        Ok(to_events(
            self.stream(&request::Watch::Create(request::WatchCreate {
                key: key.into(),
                prev_kv: true,
                ..Default::default()
            }))
            .await?,
        ))
    }

    pub async fn lease_grant(&self, ttl: Duration, id: Option<i64>) -> Result<i64, Error> {
        let response = self
            .request(&request::LeaseGrant {
                ttl: i64::try_from(ttl.as_secs()).unwrap(),
                id: id.unwrap_or(0),
            })
            .await?;
        if let Some(error) = response.error {
            return Err(Error::LeaseGrant { error });
        }
        Ok(response.id)
    }

    pub async fn lease_keep_alive(&self, id: i64) -> Result<(), Error> {
        // TODO: At the moment, grpc-gateway does not support bi-directional streaming.
        let _ = self
            .stream(&request::LeaseKeepAlive { id })
            .await?
            .try_next()
            .await?
            .context(LeaseIdNotFoundSnafu { id })?
            .ttl
            .context(LeaseIdNotFoundSnafu { id })?;
        Ok(())
    }

    pub async fn lease_revoke(&self, id: i64) -> Result<(), Error> {
        let _ = self
            .request(&request::LeaseRevoke { id })
            .await
            .map_err(|error| match error {
                Error::Grpc {
                    status: StatusCode::NOT_FOUND,
                } => Error::LeaseIdNotFound { id },
                _ => error,
            })?;
        Ok(())
    }
}

impl From<response::KeyValue> for KeyValue {
    fn from(kv: response::KeyValue) -> Self {
        (kv.key, kv.value)
    }
}

fn to_auth_header(token: &str) -> Result<HeaderValue, Error> {
    HeaderValue::from_str(token).map_err(|_| Error::InvalidToken {
        token: token.to_string(),
    })
}

fn to_key_pair<K>(range: impl RangeBounds<K>) -> (Key, Key)
where
    K: AsRef<[u8]>,
{
    let key = match range.start_bound() {
        Bound::Included(start) => Vec::from(start.as_ref()),
        Bound::Excluded(start) => {
            let mut key = Vec::from(start.as_ref());
            key.push(0);
            key
        }
        Bound::Unbounded => vec![0],
    };
    let range_end = match range.end_bound() {
        Bound::Included(end) => {
            let mut range_end = Vec::from(end.as_ref());
            range_end.push(0);
            range_end
        }
        Bound::Excluded(end) => Vec::from(end.as_ref()),
        Bound::Unbounded => vec![0],
    };
    (key, range_end)
}

fn key_plus_one(mut key: Key) -> Key {
    // Reject sentinel values.
    assert!(!key.is_empty() && key != b"\0");
    while let Some(k) = key.last_mut() {
        match k.checked_add(1) {
            Some(new_k) => {
                *k = new_k;
                break;
            }
            None => {
                key.pop();
            }
        }
    }
    if key.is_empty() {
        key.push(0);
    }
    key
}

fn to_kvs(response: response::Range) -> Vec<KeyValue> {
    response
        .kvs
        .into_iter()
        .map(|kv| (kv.key, kv.value))
        .collect()
}

fn to_events(responses: TryBoxStream<response::Watch>) -> TryBoxStream<Event> {
    fn to_stream(response: response::Watch) -> impl Stream<Item = Result<Event, Error>> + 'static {
        stream::iter(
            response
                .events
                .into_iter()
                .map(|event| {
                    Ok(match event.typ {
                        response::EventType::PUT => match event.prev_kv {
                            Some(old) => Event::Update {
                                key: event.kv.key,
                                new: event.kv.value,
                                old: old.value,
                            },
                            None => Event::Create(event.kv.into()),
                        },
                        response::EventType::DELETE => {
                            ensure!(
                                event.prev_kv.is_some(),
                                InvalidWatchDeleteSnafu {
                                    event: Box::new(event),
                                },
                            );
                            Event::Delete(event.prev_kv.unwrap().into())
                        }
                    })
                })
                .collect::<Vec<_>>(),
        )
    }

    Box::pin(responses.map_ok(to_stream).try_flatten())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_to_key_pair() {
        fn test<'a>(range: impl RangeBounds<&'a [u8]>, expect: (&[u8], &[u8])) {
            let (key, range_end) = to_key_pair(range);
            assert_eq!((key.as_slice(), range_end.as_slice()), expect);
        }

        let a = b"a".as_slice();

        test(.., (b"\0", b"\0"));
        test(a.., (b"a", b"\0"));
        test(..a, (b"\0", b"a"));
        test(..=a, (b"\0", b"a\0"));
        test(a..a, (b"a", b"a"));
        test(a..=a, (b"a", b"a\0"));

        test((Bound::Excluded(a), Bound::Excluded(a)), (b"a\0", b"a"));
    }

    #[test]
    fn test_key_plus_one() {
        fn test(key: &[u8], expect: &[u8]) {
            assert_eq!(key_plus_one(key.to_vec()), expect);
        }

        test(b"a", b"b");
        test(b"aa", b"ab");
        test(b"a\xff", b"b");
        test(b"a\xff\xff", b"b");
        test(b"\xff", b"\x00");
        test(b"\xff\xff", b"\x00");
    }

    #[test]
    #[should_panic(expected = "assertion failed: !key.is_empty() && key != b\"\\0\"")]
    fn test_key_plus_one_empty() {
        key_plus_one(Vec::new());
    }

    #[test]
    #[should_panic(expected = "assertion failed: !key.is_empty() && key != b\"\\0\"")]
    fn test_key_plus_one_zero() {
        key_plus_one(vec![0]);
    }
}
