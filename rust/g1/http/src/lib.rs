use http::Response;

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
