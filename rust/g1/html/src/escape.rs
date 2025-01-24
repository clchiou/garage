use std::fmt;
use std::io;
use std::iter;

use g1_base::fmt::Adapter;

pub(crate) struct Escaper<W>(Adapter<W>);

impl<W> Escaper<W> {
    pub(crate) fn new(output: W) -> Self {
        Self(Adapter::new(output))
    }

    pub(crate) fn into_error(self) -> Option<io::Error> {
        self.0.into_error()
    }
}

impl<W> fmt::Write for Escaper<W>
where
    W: io::Write,
{
    fn write_str(&mut self, string: &str) -> Result<(), fmt::Error> {
        escape(string).try_for_each(|piece| self.0.write_str(piece))
    }
}

fn escape(mut string: &str) -> impl Iterator<Item = &str> {
    iter::from_fn(move || {
        if string.is_empty() {
            return None;
        }
        if string.starts_with(['&', '<', '>', '"', '\'']) {
            let special;
            (special, string) = string.split_at(1);
            Some(match special {
                "&" => "&amp;",
                "<" => "&lt;",
                ">" => "&gt;",
                "\"" => "&quot;",
                "'" => "&#x27;",
                _ => std::unreachable!(),
            })
        } else {
            let piece;
            (piece, string) = match string.find(['&', '<', '>', '"', '\'']) {
                Some(i) => string.split_at(i),
                None => (string, ""),
            };
            Some(piece)
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn escaper() {
        use std::fmt::Write;

        let mut buffer = Vec::new();
        Escaper::new(&mut buffer)
            .write_str(r#"<foo bar="&spam 'egg'"/>"#)
            .unwrap();
        assert_eq!(
            buffer,
            b"&lt;foo bar=&quot;&amp;spam &#x27;egg&#x27;&quot;/&gt;",
        );
    }

    #[test]
    fn test_escape() {
        fn test(string: &str, expect: &[&str]) {
            assert_eq!(escape(string).collect::<Vec<_>>(), expect);
        }

        test("", &[]);
        test("abc{}xyz", &["abc{}xyz"]);
        test(
            r#"<foo bar="&spam 'egg'"/>"#,
            &[
                "&lt;", "foo bar=", "&quot;", "&amp;", "spam ", "&#x27;", "egg", "&#x27;",
                "&quot;", "/", "&gt;",
            ],
        );
    }
}
