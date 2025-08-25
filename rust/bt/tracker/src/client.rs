use snafu::prelude::*;
use url::Url;

use g1_url::UrlExt;

use crate::request::Request;
use crate::response::{Response, ResponseOrFailure};

#[derive(Debug, Snafu)]
pub enum Error {
    #[snafu(display("bencode error: {source}"))]
    Bencode { source: bt_bencode::error::Error },

    #[snafu(display("request failed: {reason}"))]
    Failure { reason: String },

    #[snafu(display("http error: {source}"))]
    Http { source: reqwest::Error },
}

#[derive(Clone, Debug, Default)]
pub struct Client {
    client: reqwest::Client,
}

impl Client {
    pub fn new() -> Self {
        Self {
            client: reqwest::Client::new(),
        }
    }

    pub async fn announce(&self, endpoint: Url, request: &Request) -> Result<Response, Error> {
        let request = endpoint.update_query(&[request]);
        tracing::debug!(%request);

        let response = self
            .client
            .get(request)
            .send()
            .await
            .inspect(|response| {
                tracing::debug!(
                    response.status = ?response.status(),
                    response.headers = ?response.headers(),
                );
            })
            .and_then(reqwest::Response::error_for_status)
            .context(HttpSnafu)?;

        let mut buffer = response.bytes().await.context(HttpSnafu)?;
        tracing::debug!(response.body = ?buffer);

        let ResponseOrFailure {
            failure_reason,
            response,
        } = bt_bencode::from_buf(&mut buffer).context(BencodeSnafu)?;
        if !buffer.is_empty() {
            tracing::warn!(trailing_data = ?buffer);
        }

        match failure_reason {
            None => Ok(response),
            Some(reason) => {
                tracing::debug!(?response);
                Err(Error::Failure { reason })
            }
        }
    }
}
