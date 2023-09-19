use std::error::Error;

use bytes::Bytes;
use reqwest::StatusCode;

use bittorrent_metainfo::Metainfo;

use crate::{
    request::{AnnounceUrls, Request},
    response::ResponseOwner,
};

#[derive(Debug)]
pub struct Client {
    urls: AnnounceUrls,
}

impl Client {
    pub fn new(metainfo: &Metainfo) -> Self {
        Self {
            urls: AnnounceUrls::new(metainfo),
        }
    }

    pub async fn get(
        &mut self,
        request: &Request<'_>,
    ) -> Result<ResponseOwner<Bytes>, Box<dyn Error>> {
        let mut announce_url = self.urls.url().to_string();
        announce_url.push('?');
        request.append_url_query_to(&mut announce_url);
        tracing::debug!(announce_url);

        let response = reqwest::get(&announce_url).await?;
        if response.status() == StatusCode::OK {
            tracing::debug!(response.headers = ?response.headers());
            self.urls.succeed();
        } else {
            // At the moment, we do not implement retry.
            tracing::warn!(
                response.status = ?response.status(),
                response.headers = ?response.headers(),
            );
            self.urls.fail()?;
        }

        let response = response.bytes().await?;
        let response = ResponseOwner::try_from(response)?;
        tracing::debug!(response.body = ?response);
        Ok(response)
    }
}
