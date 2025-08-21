use std::borrow::{Borrow, Cow};
use std::collections::BTreeMap;
use std::collections::btree_map;
use std::mem;

use form_urlencoded::Serializer;
use url::Url;

pub trait UrlExt {
    // We need this due to the idiosyncrasy of `Url::join`.
    fn ensure_trailing_slash(self) -> Self;

    fn parse_query<T>(&self) -> Result<T, T::Error>
    where
        T: ParseQuery;

    // We do not preserve either the order or duplicated URL query parameters.
    fn update_query(self, updates: &[&dyn UpdateQuery]) -> Self;
}

//
// NOTE: Implementers of `ParseQuery` and `UpdateQuery` must maintain backward compatibility, as
// query parameters are generally part of the public interface.
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

pub trait UpdateQuery {
    // Its signature is a bit unusual in order to keep the trait `dyn`-compatible.
    fn update_query<'a: 'b, 'b>(&'a self, builder: &mut QueryBuilder<'b>);

    // NOTE: It skips raw query pairs.
    fn query_pairs(&self) -> QueryPairs
    where
        Self: Sized,
    {
        let mut builder = QueryBuilder::new();
        self.update_query(&mut builder);
        builder.pairs.into_iter()
    }
}

// Use `BTreeMap` because it is nice to have a deterministic output.
#[derive(Debug)]
pub struct QueryBuilder<'a> {
    pairs: BTreeMap<Cow<'a, str>, Cow<'a, str>>,
    // It is weird that we split query parameters into two independent groups, but given that
    // `pairs` should be the norm and `raw_pairs` the exception, it is probably fine.
    raw_pairs: BTreeMap<Cow<'a, str>, Cow<'a, str>>,
}

pub type QueryPairs<'a> = btree_map::IntoIter<Cow<'a, str>, Cow<'a, str>>;

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

    fn update_query(mut self, updates: &[&dyn UpdateQuery]) -> Self {
        let mut builder = QueryBuilder::from_url(&self);
        for update in updates {
            update.update_query(&mut builder);
        }
        let QueryBuilder { pairs, raw_pairs } = builder;

        if pairs.is_empty() && raw_pairs.is_empty() {
            self.set_query(None);
            return self;
        }

        let mut serializer = Serializer::new(String::new());
        for (key, value) in pairs {
            serializer.append_pair(&key, &value);
        }

        let mut serializer = serializer.finish();
        let mut first = serializer.is_empty();
        for (raw_key, raw_value) in raw_pairs {
            if !mem::take(&mut first) {
                serializer.push('&');
            }
            serializer.push_str(&raw_key);
            serializer.push('=');
            serializer.push_str(&raw_value);
        }

        self.set_query(Some(&serializer));
        self
    }
}

impl<'a> QueryBuilder<'a> {
    fn from_url(url: &'a Url) -> Self {
        Self {
            pairs: url.query_pairs().collect(),
            raw_pairs: BTreeMap::new(),
        }
    }

    fn new() -> Self {
        Self {
            pairs: BTreeMap::new(),
            raw_pairs: BTreeMap::new(),
        }
    }

    pub fn insert<K, V>(&mut self, key: K, value: V) -> &mut Self
    where
        Cow<'a, str>: From<K>,
        Cow<'a, str>: From<V>,
    {
        self.pairs.insert(key.into(), value.into());
        self
    }

    pub fn remove<Q>(&mut self, key: &Q) -> &mut Self
    where
        Cow<'a, str>: Borrow<Q>,
        Q: Ord + ?Sized,
    {
        self.pairs.remove(key);
        self
    }

    /// Inserts a raw query parameter.
    ///
    /// NOTE: The caller has to properly percent-encode both the key and the value.
    pub fn insert_raw<K, V>(&mut self, key: K, value: V) -> &mut Self
    where
        Cow<'a, str>: From<K>,
        Cow<'a, str>: From<V>,
    {
        self.raw_pairs.insert(key.into(), value.into());
        self
    }

    pub fn remove_raw<Q>(&mut self, key: &Q) -> &mut Self
    where
        Cow<'a, str>: Borrow<Q>,
        Q: Ord + ?Sized,
    {
        self.raw_pairs.remove(key);
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
            for (key, value) in query_pairs {
                match &*key {
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

    impl UpdateQuery for Option<Param> {
        fn update_query<'a: 'b, 'b>(&'a self, builder: &mut QueryBuilder<'b>) {
            match self {
                Some(this) => builder.insert("x", &this.0).insert("y", &this.1),
                None => builder.remove("x").remove("y"),
            };
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

    #[test]
    fn insert_raw() {
        struct Query(bool, bool);

        impl UpdateQuery for Query {
            fn update_query<'a: 'b, 'b>(&'a self, builder: &mut QueryBuilder<'b>) {
                if self.0 {
                    builder.insert("spam egg", "Hello, World!");
                }
                if self.1 {
                    builder
                        .insert_raw("spam%20egg", "Hello%2C%20World%21")
                        .insert_raw("foo", "bar");
                }
            }
        }

        assert_eq!(
            u("http://127.0.0.1/").update_query(&[&Query(false, false)]),
            u("http://127.0.0.1/"),
        );

        assert_eq!(
            u("http://127.0.0.1/").update_query(&[&Query(true, false)]),
            u("http://127.0.0.1/?spam+egg=Hello%2C+World%21"),
        );

        assert_eq!(
            u("http://127.0.0.1/").update_query(&[&Query(false, true)]),
            u("http://127.0.0.1/?foo=bar&spam%20egg=Hello%2C%20World%21"),
        );

        assert_eq!(
            u("http://127.0.0.1/").update_query(&[&Query(true, true)]),
            u(
                "http://127.0.0.1/?spam+egg=Hello%2C+World%21&foo=bar&spam%20egg=Hello%2C%20World%21"
            ),
        );
    }
}
