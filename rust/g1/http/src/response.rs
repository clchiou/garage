use http::Error;
use http::header::{HeaderName, HeaderValue};
use http::response::{Builder, Response};

pub trait BuilderExt: Sized {
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

impl BuilderExt for Builder {
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

pub trait ResponseExt {
    fn is_cloudflare_challenge_page(&self) -> bool;
}

impl<T> ResponseExt for Response<T> {
    fn is_cloudflare_challenge_page(&self) -> bool {
        // The Cloudflare Challenge Page can be detected this way [1].
        // [1]: https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/
        self.headers()
            .get("cf-mitigated")
            .inspect(|value| assert_eq!(*value, "challenge"))
            .is_some()
    }
}
