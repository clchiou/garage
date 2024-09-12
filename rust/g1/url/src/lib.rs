use url::Url;

// We need this due to the idiosyncrasy of `Url::join`.
pub fn ensure_trailing_slash(mut url: Url) -> Url {
    let path = url.path();
    if !path.ends_with('/') {
        url.set_path(&std::format!("{path}/"));
    }
    url
}

#[cfg(test)]
mod tests {
    use super::*;

    fn u(url: &str) -> Url {
        url.parse().unwrap()
    }

    #[test]
    fn test_ensure_trailing_slash() {
        fn test(url: &str, expect: &str) {
            assert_eq!(ensure_trailing_slash(u(url)).path(), expect);
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
