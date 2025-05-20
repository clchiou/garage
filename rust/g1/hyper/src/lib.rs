use std::cmp;
use std::marker::Unpin;

use async_trait::async_trait;
use bytes::{BufMut, Bytes, BytesMut};
use futures::stream::TryStreamExt;
use http_body_util::BodyDataStream;
use hyper::body::Body;
use hyper::header::{ACCEPT_LANGUAGE, CONTENT_LENGTH, HeaderValue};
use hyper::{Error, Request};
use url::Url;

pub trait RequestExt {
    /// Parses request URI and returns a `url::Url`.
    ///
    /// We provide this function because `url::Url` is handier than `hyper::Uri`.  Note that,
    /// according to [RFC 7230], a request target is typically a path with an optional query
    /// string.
    ///
    /// [RFC 7230]: https://datatracker.ietf.org/doc/html/rfc7230#section-5.3
    fn url(&self, base: Url) -> Url;

    fn accept_language(&self) -> impl Iterator<Item = Result<(&str, f64), &HeaderValue>>;

    fn content_length(&self) -> Result<Option<u64>, &HeaderValue>;
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BodyLimitExceededError;

#[async_trait]
pub trait RequestBodyExt {
    async fn read_body_to_end(
        &mut self,
        limit: usize,
    ) -> Result<Result<Bytes, BodyLimitExceededError>, Error>;
}

//
// Implementer's Notes: When parsing HTTP headers, note that some headers may appear multiple
// times, as specified in [RFC 2616].
//
// [RFC 2616]: https://datatracker.ietf.org/doc/html/rfc2616#section-4.2
//

impl<T> RequestExt for Request<T> {
    fn url(&self, mut base: Url) -> Url {
        let uri = self.uri();
        base.set_path(uri.path());
        base.set_query(uri.query());
        base
    }

    fn accept_language(&self) -> impl Iterator<Item = Result<(&str, f64), &HeaderValue>> {
        self.headers()
            .get_all(ACCEPT_LANGUAGE)
            .into_iter()
            .flat_map(|value| ResultIter::new(parse_accept_language(value)))
    }

    fn content_length(&self) -> Result<Option<u64>, &HeaderValue> {
        self.headers()
            .get(CONTENT_LENGTH)
            .map(|value| {
                value
                    .to_str()
                    .map_err(|_| value)?
                    .trim()
                    .parse()
                    .map_err(|_| value)
            })
            .transpose()
    }
}

#[async_trait]
impl<T> RequestBodyExt for Request<T>
where
    T: Body<Data = Bytes, Error = Error> + Send + Unpin,
{
    async fn read_body_to_end(
        &mut self,
        limit: usize,
    ) -> Result<Result<Bytes, BodyLimitExceededError>, Error> {
        let mut body = BytesMut::with_capacity(cmp::min(
            self.content_length()
                .ok()
                .flatten()
                .map_or(0, |x| x.try_into().unwrap_or(0)),
            limit,
        ));
        let mut frames = BodyDataStream::new(self.body_mut());
        while let Some(frame) = frames.try_next().await? {
            if body.len() + frame.len() > limit {
                return Ok(Err(BodyLimitExceededError));
            }
            body.put_slice(&frame);
        }
        Ok(Ok(body.into()))
    }
}

// https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Language
fn parse_accept_language(
    value: &HeaderValue,
) -> Result<impl Iterator<Item = (&str, f64)>, &HeaderValue> {
    macro_rules! re {
        ($func:ident, $arg:ident $(,)?) => {
            lazy_regex::$func!(
                r"(?x-u)
                ^
                \s*
                ( [A-Za-z0-9-]+ | \* )
                (?: \s* ; \s* q \s* = \s* ( 0 (?: \. [0-9]+ )? | 1 (?: \. 0+ )? ) )?
                \s*
                $
                ",
                $arg,
            )
        };
    }

    let pairs = value.to_str().map_err(|_| value)?;
    if pairs.split(',').all(|pair| re!(regex_is_match, pair)) {
        Ok(pairs.split(',').map(|pair| {
            let (_, l, q) = re!(regex_captures, pair).expect("parse_accept_language");
            (l, parse_quality_value(q).expect("parse_quality_value"))
        }))
    } else {
        Err(value)
    }
}

// https://developer.mozilla.org/en-US/docs/Glossary/Quality_values
fn parse_quality_value(value: &str) -> Result<f64, &str> {
    if value.is_empty() {
        Ok(1.0)
    } else if lazy_regex::regex_is_match!(
        r"(?x-u) ^ (?: 0 (?: \. [0-9]+ )? | 1 (?: \. 0+ )? ) $",
        value,
    ) {
        Ok(value.parse().expect("parse_quality_value"))
    } else {
        Err(value)
    }
}

struct ResultIter<I, E>(Result<I, Option<E>>);

impl<I, E> ResultIter<I, E> {
    fn new(result: Result<I, E>) -> Self {
        match result {
            Ok(iter) => ResultIter(Ok(iter)),
            Err(error) => ResultIter(Err(Some(error))),
        }
    }
}

impl<I, T, E> Iterator for ResultIter<I, E>
where
    I: Iterator<Item = T>,
{
    type Item = Result<T, E>;

    fn next(&mut self) -> Option<Self::Item> {
        match &mut self.0 {
            Ok(iter) => iter.next().map(Ok),
            Err(error) => error.take().map(Err),
        }
    }
}

#[cfg(test)]
mod tests {
    use futures::stream;
    use http_body_util::StreamBody;
    use hyper::body::Frame;

    use super::*;

    fn u(url: &str) -> Url {
        url.parse().unwrap()
    }

    #[test]
    fn url() {
        let base = u("http://localhost:8000/some/path?foo=bar#spam");
        for (uri, expect) in [
            ("/", "http://localhost:8000/#spam"),
            ("/a/b/c", "http://localhost:8000/a/b/c#spam"),
            ("/?abc=xyz", "http://localhost:8000/?abc=xyz#spam"),
            ("/a/b/c?xyz#frag", "http://localhost:8000/a/b/c?xyz#spam"),
        ] {
            assert_eq!(
                Request::get(uri).body(()).unwrap().url(base.clone()),
                u(expect),
            );
        }
    }

    #[test]
    fn accept_language() {
        fn test(values: &[&'static str], expect: &[Result<(&str, f64), &str>]) {
            let mut builder = Request::get("/");
            for value in values {
                builder = builder.header(ACCEPT_LANGUAGE, HeaderValue::from_static(value));
            }
            assert_eq!(
                builder
                    .body(())
                    .unwrap()
                    .accept_language()
                    .map(|result| match result {
                        Ok((l, q)) => Ok((l.to_string(), q)),
                        Err(h) => Err(h.to_str().unwrap().to_string()),
                    })
                    .collect::<Vec<_>>(),
                expect
                    .iter()
                    .map(|result| match result {
                        Ok((l, q)) => Ok((l.to_string(), *q)),
                        Err(h) => Err(h.to_string()),
                    })
                    .collect::<Vec<_>>(),
            );
        }

        test(&[], &[]);
        test(&["*"], &[Ok(("*", 1.0))]);
        test(
            &["en-US", "en;q=0.5, *;q=0.1"],
            &[Ok(("en-US", 1.0)), Ok(("en", 0.5)), Ok(("*", 0.1))],
        );

        test(
            &["en", " x;q ", "*, a-b-c, *;q=0.5"],
            &[
                Ok(("en", 1.0)),
                Err(" x;q "),
                Ok(("*", 1.0)),
                Ok(("a-b-c", 1.0)),
                Ok(("*", 0.5)),
            ],
        );
    }

    #[test]
    fn content_length() {
        fn test(values: &[&'static str], expect: Result<Option<u64>, &str>) {
            let mut builder = Request::get("/");
            for value in values {
                builder = builder.header(CONTENT_LENGTH, HeaderValue::from_static(value));
            }
            assert_eq!(
                builder
                    .body(())
                    .unwrap()
                    .content_length()
                    .map_err(|h| h.to_str().unwrap().to_string()),
                expect.map_err(|h| h.to_string()),
            );
        }

        test(&[], Ok(None));
        test(&["0"], Ok(Some(0)));
        test(&["1"], Ok(Some(1)));
        test(&[" 1001 "], Ok(Some(1001)));
        test(&["123", "456"], Ok(Some(123)));

        test(&["0x1", "456"], Err("0x1"));
        test(&["123", "0x1"], Ok(Some(123)));

        test(&[""], Err(""));

        test(&["0x1"], Err("0x1"));

        test(&["-1"], Err("-1"));

        test(&["18446744073709551615"], Ok(Some(18446744073709551615)));
        test(&["18446744073709551616"], Err("18446744073709551616"));
    }

    #[tokio::test]
    async fn read_body_to_end() {
        fn b(data: &'static [u8]) -> Bytes {
            data.into()
        }

        async fn run(body: &'static [u8], limit: usize) -> Result<Bytes, BodyLimitExceededError> {
            Request::get("/")
                .header(CONTENT_LENGTH, u64::MAX)
                .body(StreamBody::new(stream::iter(
                    body.chunks(1).map(|chunk| Ok(Frame::data(chunk.into()))),
                )))
                .unwrap()
                .read_body_to_end(limit)
                .await
                .unwrap()
        }

        assert_eq!(run(b"", 2).await, Ok(b(b"")));
        assert_eq!(run(b"", 1).await, Ok(b(b"")));
        assert_eq!(run(b"", 0).await, Ok(b(b"")));

        assert_eq!(run(b"x", 2).await, Ok(b(b"x")));
        assert_eq!(run(b"x", 1).await, Ok(b(b"x")));
        assert_eq!(run(b"x", 0).await, Err(BodyLimitExceededError));

        assert_eq!(run(b"Hello, World!", 14).await, Ok(b(b"Hello, World!")));
        assert_eq!(run(b"Hello, World!", 13).await, Ok(b(b"Hello, World!")));
        assert_eq!(run(b"Hello, World!", 12).await, Err(BodyLimitExceededError));
    }

    #[test]
    fn test_parse_accept_language() {
        fn test_ok(value: &'static str, expect: &[(&str, f64)]) {
            assert_eq!(
                parse_accept_language(&HeaderValue::from_static(value))
                    .unwrap()
                    .collect::<Vec<_>>(),
                expect,
            );
        }

        fn test_err(value: &'static str) {
            assert!(parse_accept_language(&HeaderValue::from_static(value)).is_err());
        }

        test_ok("*", &[("*", 1.0)]);
        test_ok(
            "  en-US  ,  en  ;  q  =  0.5  ,  *;q=1  ",
            &[("en-US", 1.0), ("en", 0.5), ("*", 1.0)],
        );

        test_err("");
        test_err("   ");
        test_err(" , ");
        test_err("en_US");
        test_err("en;");
        test_err("en;q");
        test_err("en;q=");
        test_err("en;q=1.1");
        test_err("en;q=2");
    }

    #[test]
    fn test_parse_quality_value() {
        assert_eq!(parse_quality_value(""), Ok(1.0));

        assert_eq!(parse_quality_value("0"), Ok(0.0));
        assert_eq!(parse_quality_value("0.0"), Ok(0.0));
        assert_eq!(parse_quality_value("0.00000"), Ok(0.0));
        assert_eq!(parse_quality_value("0.246"), Ok(0.246));
        assert_eq!(parse_quality_value("1"), Ok(1.0));
        assert_eq!(parse_quality_value("1.0"), Ok(1.0));
        assert_eq!(parse_quality_value("1.00000"), Ok(1.0));

        assert_eq!(parse_quality_value(" "), Err(" "));
        assert_eq!(parse_quality_value(" 0 "), Err(" 0 "));
        assert_eq!(parse_quality_value("0x1"), Err("0x1"));
        assert_eq!(parse_quality_value("0."), Err("0."));
        assert_eq!(parse_quality_value("1."), Err("1."));
        assert_eq!(parse_quality_value("1.1"), Err("1.1"));
        assert_eq!(parse_quality_value("2"), Err("2"));
    }

    #[test]
    fn result_iter() {
        fn r(result: Result<Vec<u8>, u8>) -> Result<impl Iterator<Item = u8>, u8> {
            match result {
                Ok(xs) => Ok(xs.into_iter()),
                Err(x) => Err(x),
            }
        }

        assert_eq!(
            ResultIter::new(r(Ok(vec![1, 2, 3]))).collect::<Vec<_>>(),
            [Ok(1), Ok(2), Ok(3)],
        );
        assert_eq!(ResultIter::new(r(Err(4))).collect::<Vec<_>>(), [Err(4)]);
    }
}
