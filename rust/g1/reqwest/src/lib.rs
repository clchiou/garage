#![feature(iterator_try_collect)]

mod serde_impl;

use std::sync::Arc;
use std::time::Duration;

use regex::Regex;
use reqwest::header::{HeaderMap, HeaderValue};
use reqwest::{Client, Error, Proxy, Url};
use serde::{Deserialize, Serialize};
use serde_with::skip_serializing_none;

//
// Implementer's Notes:
//
// * Our builder should only override fields of the input builder that are explicitly specified.
//   This is why we declare `Option<bool>` instead of a simple `bool` below.
//
// * For collection-typed fields such as `default_headers` and `proxy`, `reqwest::ClientBuilder`
//   does not provide an interface for element removal, so neither can we.
//

#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default, deny_unknown_fields)]
pub struct ClientBuilder {
    #[serde(with = "serde_impl::opt_duration")]
    pub pool_idle_timeout: Option<Duration>,
    pub pool_max_idle_per_host: Option<usize>,

    #[serde(with = "serde_impl::opt_duration")]
    pub connect_timeout: Option<Duration>,
    #[serde(with = "serde_impl::opt_duration")]
    pub read_timeout: Option<Duration>,
    #[serde(with = "serde_impl::opt_duration")]
    pub timeout: Option<Duration>,

    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub proxy: Vec<ProxyBuilder>,

    pub danger_accept_invalid_certs: Option<bool>,

    pub brotli: Option<bool>,
    pub deflate: Option<bool>,
    pub gzip: Option<bool>,
    pub zstd: Option<bool>,

    // `default_headers` can be overridden by more specific fields, such as `user_agent`.
    #[serde(with = "serde_impl::opt_header_map")]
    pub default_headers: Option<HeaderMap>,
    #[serde(with = "serde_impl::opt_header_value")]
    pub user_agent: Option<HeaderValue>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProxyBuilder {
    #[serde(flatten)]
    pub match_: ProxyMatch,
    pub proxy: Url,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields, rename_all = "snake_case")]
pub enum ProxyMatch {
    Scheme(Scheme),
    Host(#[serde(with = "serde_impl::regex")] (Arc<str>, Regex)),
}

impl PartialEq for ProxyMatch {
    fn eq(&self, other: &Self) -> bool {
        match (self, other) {
            (Self::Scheme(this), Self::Scheme(that)) => this == that,
            (Self::Host((this, _)), Self::Host((that, _))) => this == that,
            _ => false,
        }
    }
}

impl Eq for ProxyMatch {}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields, rename_all = "snake_case")]
pub enum Scheme {
    All,
    Http,
    Https,
}

impl ClientBuilder {
    pub fn build(self) -> Result<Client, Error> {
        self.build_from(reqwest::ClientBuilder::new())
    }

    pub fn build_from(self, builder: reqwest::ClientBuilder) -> Result<Client, Error> {
        self.merge_into(builder).and_then(|builder| builder.build())
    }

    pub fn merge_into(
        self,
        mut builder: reqwest::ClientBuilder,
    ) -> Result<reqwest::ClientBuilder, Error> {
        macro_rules! set {
            ($name:ident $(,)?) => {
                if let Some(x) = self.$name {
                    builder = builder.$name(x);
                }
            };
        }

        set!(pool_idle_timeout);
        set!(pool_max_idle_per_host);

        set!(connect_timeout);
        set!(read_timeout);
        set!(timeout);

        for proxy in self.proxy {
            builder = builder.proxy(proxy.build()?);
        }

        set!(danger_accept_invalid_certs);

        set!(brotli);
        set!(deflate);
        set!(gzip);
        set!(zstd);

        set!(default_headers);
        set!(user_agent);

        Ok(builder)
    }
}

impl ProxyBuilder {
    pub fn build(self) -> Result<Proxy, Error> {
        let Self { match_, proxy } = self;
        match match_ {
            ProxyMatch::Scheme(Scheme::All) => Proxy::all(proxy),
            ProxyMatch::Scheme(Scheme::Http) => Proxy::http(proxy),
            ProxyMatch::Scheme(Scheme::Https) => Proxy::https(proxy),
            ProxyMatch::Host((_, host)) => Ok(Proxy::custom(move |url| {
                host.is_match(url.host_str()?).then(|| proxy.clone())
            })),
        }
    }
}

pub trait MergeFrom<Builder>: Sized {
    fn merge_from(self, builder: Builder) -> Result<Self, Error>;
}

impl MergeFrom<ClientBuilder> for reqwest::ClientBuilder {
    fn merge_from(self, builder: ClientBuilder) -> Result<Self, Error> {
        builder.merge_into(self)
    }
}

impl MergeFrom<Option<ClientBuilder>> for reqwest::ClientBuilder {
    fn merge_from(self, builder: Option<ClientBuilder>) -> Result<Self, Error> {
        match builder {
            Some(builder) => self.merge_from(builder),
            None => Ok(self),
        }
    }
}
