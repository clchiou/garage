use url::Url;

// We need this due to the idiosyncrasy of `Url::join`.
pub fn ensure_trailing_slash(mut url: Url) -> Url {
    let path = url.path();
    if path != "/" && !path.ends_with('/') {
        let mut path = path.to_string();
        path.push('/');
        url.set_path(&path);
    }
    url
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ensure_trailing_slash() {
        fn test(url: &str, expect: &str) {
            assert_eq!(
                ensure_trailing_slash(Url::parse(url).unwrap()).path(),
                expect,
            );
        }

        test("http://127.0.0.1:8000", "/");
        test("http://127.0.0.1:8000/", "/");
        test("http://127.0.0.1:8000/a", "/a/");
        test("http://127.0.0.1:8000/a/", "/a/");
        test("http://127.0.0.1:8000/foo/bar", "/foo/bar/");
    }
}
