use url::Url;

pub trait UrlExt {
    // We need this due to the idiosyncrasy of `Url::join`.
    fn ensure_trailing_slash(self) -> Self;
}

impl UrlExt for Url {
    fn ensure_trailing_slash(mut self) -> Self {
        let path = self.path();
        if !path.ends_with('/') {
            self.set_path(&std::format!("{path}/"));
        }
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn u(url: &str) -> Url {
        url.parse().unwrap()
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
}
