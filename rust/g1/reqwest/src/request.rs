use http::Error;
use http::header::{HeaderName, HeaderValue};
use reqwest::RequestBuilder;

pub trait RequestBuilderExt: Sized {
    fn header_optional<K, V>(self, key: K, value: Option<V>) -> Self
    where
        HeaderName: TryFrom<K, Error: Into<Error>>,
        HeaderValue: TryFrom<V, Error: Into<Error>>,
    {
        self.headers_extend(value.map(|value| (key, value)))
    }

    fn headers_extend<I, K, V>(self, iter: I) -> Self
    where
        I: IntoIterator<Item = (K, V)>,
        HeaderName: TryFrom<K, Error: Into<Error>>,
        HeaderValue: TryFrom<V, Error: Into<Error>>;
}

impl RequestBuilderExt for RequestBuilder {
    fn headers_extend<I, K, V>(self, iter: I) -> Self
    where
        I: IntoIterator<Item = (K, V)>,
        HeaderName: TryFrom<K, Error: Into<Error>>,
        HeaderValue: TryFrom<V, Error: Into<Error>>,
    {
        let mut this = self;
        for (key, value) in iter {
            this = this.header(key, value);
        }
        this
    }
}
