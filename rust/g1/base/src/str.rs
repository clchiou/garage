use std::cmp;

pub trait StrExt {
    // TODO: Deprecate this when/if the `str` type provides a `chunks` method.
    fn chunks(&self, chunk_size: usize) -> impl Iterator<Item = &str>;
}

impl StrExt for str {
    fn chunks(&self, chunk_size: usize) -> impl Iterator<Item = &str> {
        assert!(chunk_size != 0);
        (0..self.len())
            .step_by(chunk_size)
            .map(move |i| &self[i..cmp::min(i + chunk_size, self.len())])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[should_panic(expected = "assertion failed: chunk_size != 0")]
    fn zero_chunk_size() {
        let _ = "".chunks(0);
    }

    #[test]
    fn chunks() {
        fn test(string: &str, chunk_size: usize, expect: Vec<&str>) {
            assert_eq!(string.chunks(chunk_size).collect::<Vec<_>>(), expect);
        }

        test("", 1, Vec::new());

        test("a", 1, vec!["a"]);
        test("ab", 1, vec!["a", "b"]);
        test("abc", 1, vec!["a", "b", "c"]);

        test("a", 2, vec!["a"]);
        test("ab", 2, vec!["ab"]);
        test("abc", 2, vec!["ab", "c"]);
        test("abcd", 2, vec!["ab", "cd"]);
        test("abcdf", 2, vec!["ab", "cd", "f"]);
    }
}
