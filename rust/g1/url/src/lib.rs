use std::borrow::Cow;
use std::collections::BTreeMap;

use url::Url;

pub trait UrlExt {
    // We need this due to the idiosyncrasy of `Url::join`.
    fn ensure_trailing_slash(self) -> Self;

    fn parse_query<T>(&self) -> Result<T, T::Error>
    where
        T: ParseQuery;

    // We do not preserve either the order or duplicated URL query parameters.
    fn update_query(self, vars: &[&dyn ToQuery]) -> Self;
}

//
// NOTE: Implementers of `ParseQuery` and `ToQuery` must maintain backward compatibility, as query
// parameters are generally part of the public interface.
//

// NOTE: I did a few experiments to make an implementer `T` borrow from `query_pairs`, but they
// were unsuccessful.  The primary reason is that `query_pairs` returns `Cow`s, meaning the value
// may or may not be borrowing from `Url`.  As a result, caller is often forced to create a
// self-referential struct that owns the `Cow` values and `T` that points back to `Cow`.  This adds
// unnecessary complexity for little benefit.
pub trait ParseQuery: Sized {
    type Error;

    fn parse_query<'a, I>(query_pairs: I) -> Result<Self, Self::Error>
    where
        I: Iterator<Item = (Cow<'a, str>, Cow<'a, str>)>;
}

pub trait ToQuery {
    // For now, we return a `Vec` because it is much easier than returning an iterator trait
    // object.
    fn to_query(&self) -> Vec<(&str, Option<Cow<'_, str>>)>;
}

impl UrlExt for Url {
    fn ensure_trailing_slash(mut self) -> Self {
        let path = self.path();
        if !path.ends_with('/') {
            self.set_path(&std::format!("{path}/"));
        }
        self
    }

    fn parse_query<T>(&self) -> Result<T, T::Error>
    where
        T: ParseQuery,
    {
        T::parse_query(self.query_pairs())
    }

    fn update_query(mut self, vars: &[&dyn ToQuery]) -> Self {
        // It is nice to have a deterministic output.
        let mut query: BTreeMap<_, _> = self.query_pairs().into_owned().collect();
        for var in vars {
            for (name, value) in var.to_query() {
                match value {
                    Some(value) => query.insert(name.into(), value.into()),
                    None => query.remove(name),
                };
            }
        }
        if query.is_empty() {
            self.set_query(None);
        } else {
            let mut ps = self.query_pairs_mut();
            ps.clear();
            ps.extend_pairs(query);
        }
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Clone, Debug, Eq, PartialEq)]
    struct Param(String, String);

    impl ParseQuery for Option<Param> {
        type Error = (Option<String>, Option<String>);

        fn parse_query<'a, I>(query_pairs: I) -> Result<Self, Self::Error>
        where
            I: Iterator<Item = (Cow<'a, str>, Cow<'a, str>)>,
        {
            let mut x = None;
            let mut y = None;
            for (name, value) in query_pairs {
                match &*name {
                    "x" => x = Some(value),
                    "y" => y = Some(value),
                    _ => {}
                }
            }
            match (x, y) {
                (Some(x), Some(y)) => Ok(Some(Param(x.into_owned(), y.into_owned()))),
                (None, None) => Ok(None),
                (x, y) => Err((x.map(Cow::into_owned), y.map(Cow::into_owned))),
            }
        }
    }

    impl ToQuery for Option<Param> {
        fn to_query(&self) -> Vec<(&str, Option<Cow<'_, str>>)> {
            match self {
                Some(this) => vec![("x", Some((&this.0).into())), ("y", Some((&this.1).into()))],
                None => vec![("x", None), ("y", None)],
            }
        }
    }

    fn u(url: &str) -> Url {
        url.parse().unwrap()
    }

    fn p(x: &str, y: &str) -> Param {
        Param(x.to_string(), y.to_string())
    }

    #[test]
    fn ensure_trailing_slash() {
        fn test(url: &str, expect: &str) {
            assert_eq!(u(url).ensure_trailing_slash().path(), expect);
        }

        assert_eq!(u("http://127.0.0.1:8000").path(), "/");
        assert_eq!(
            u("http://127.0.0.1:8000").join("a/b/c").unwrap().path(),
            "/a/b/c",
        );

        assert_eq!(
            u("http://127.0.0.1:8000/with/out/slash")
                .join("a/b/c")
                .unwrap()
                .path(),
            "/with/out/a/b/c",
        );

        assert_eq!(
            u("http://127.0.0.1:8000/with/slash/")
                .join("a/b/c")
                .unwrap()
                .path(),
            "/with/slash/a/b/c",
        );

        test("http://127.0.0.1:8000", "/");
        test("http://127.0.0.1:8000/", "/");
        test("http://127.0.0.1:8000/a", "/a/");
        test("http://127.0.0.1:8000/a/", "/a/");
        test("http://127.0.0.1:8000/foo/bar", "/foo/bar/");
        test("http://127.0.0.1:8000/foo/bar/", "/foo/bar/");
    }

    #[test]
    fn parse_query() {
        for (url, expect) in [
            ("http://127.0.0.1/a/b/c", Ok(None)),
            ("http://127.0.0.1/a/b/c?z=1", Ok(None)),
            (
                "http://127.0.0.1/a/b/c?x=1&y=2&x=foo&y=bar",
                Ok(Some(p("foo", "bar"))),
            ),
            (
                "http://127.0.0.1/a/b/c?x=",
                Err((Some("".to_string()), None)),
            ),
            (
                "http://127.0.0.1/a/b/c?y=",
                Err((None, Some("".to_string()))),
            ),
        ] {
            assert_eq!(u(url).parse_query::<Option<Param>>(), expect);
        }
    }

    #[test]
    fn update_query() {
        assert_eq!(
            u("http://127.0.0.1/a/b/c?y=2&x=1&z=foo&z=3").update_query(&[]),
            u("http://127.0.0.1/a/b/c?x=1&y=2&z=3"),
        );

        assert_eq!(
            u("http://127.0.0.1/a/b/c?y=2&x=1").update_query(&[&Option::<Param>::None]),
            u("http://127.0.0.1/a/b/c"),
        );
        assert_eq!(
            u("http://127.0.0.1/a/b/c?y=2&x=1&z=3").update_query(&[&Option::<Param>::None]),
            u("http://127.0.0.1/a/b/c?z=3"),
        );

        assert_eq!(
            u("http://127.0.0.1/a/b/c?z=3").update_query(&[&Some(p("foo", "bar"))]),
            u("http://127.0.0.1/a/b/c?x=foo&y=bar&z=3"),
        );
        assert_eq!(
            u("http://127.0.0.1/a/b/c?y=2&x=1&z=3").update_query(&[&Some(p("foo", "bar"))]),
            u("http://127.0.0.1/a/b/c?x=foo&y=bar&z=3"),
        );

        assert_eq!(
            u("http://127.0.0.1/a/b/c?y=2&x=1&a=3")
                .update_query(&[&Option::<Param>::None, &Some(p("foo", "bar"))]),
            u("http://127.0.0.1/a/b/c?a=3&x=foo&y=bar"),
        );
        assert_eq!(
            u("http://127.0.0.1/a/b/c?y=2&x=1&a=3")
                .update_query(&[&Some(p("foo", "bar")), &Option::<Param>::None]),
            u("http://127.0.0.1/a/b/c?a=3"),
        );
        assert_eq!(
            u("http://127.0.0.1/a/b/c?a=3")
                .update_query(&[&Some(p("1", "2")), &Some(p("foo", "bar"))]),
            u("http://127.0.0.1/a/b/c?a=3&x=foo&y=bar"),
        );
    }
}
