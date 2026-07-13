use std::borrow::Cow;

use encoding_rs::UTF_8;
use mime::Mime;
use reqwest::Response;
use reqwest::header::CONTENT_TYPE;

pub trait ResponseExt {
    fn is_cloudflare_challenge_page(&self) -> bool;

    // `Response::text` is copied here because it consumes the `Response` value and performs a
    // lossy conversion, making it sometimes unwieldy.
    fn encoding(&self) -> Encoding;
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Encoding(pub &'static encoding_rs::Encoding);

impl ResponseExt for Response {
    fn is_cloudflare_challenge_page(&self) -> bool {
        // The Cloudflare Challenge Page can be detected this way [1].
        // [1]: https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/
        self.headers()
            .get("cf-mitigated")
            .inspect(|value| assert_eq!(*value, "challenge"))
            .is_some()
    }

    fn encoding(&self) -> Encoding {
        let content_type = self
            .headers()
            .get(CONTENT_TYPE)
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.parse::<Mime>().ok());
        let encoding_name = content_type
            .as_ref()
            .and_then(|mime| mime.get_param("charset").map(|charset| charset.as_str()))
            .unwrap_or("utf-8");
        Encoding(encoding_rs::Encoding::for_label(encoding_name.as_bytes()).unwrap_or(UTF_8))
    }
}

impl Encoding {
    pub fn decode<'a>(&self, bytes: &'a [u8]) -> Cow<'a, str> {
        let (string, _, _) = self.0.decode(bytes);
        string
    }
}
