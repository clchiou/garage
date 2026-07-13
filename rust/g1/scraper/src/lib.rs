#![cfg_attr(test, feature(assert_matches))]

use std::borrow::Cow;

use scraper::{CaseSensitivity, ElementRef};

pub trait ElementRefExt<'a> {
    fn has_class(&self, class: &str) -> bool;

    fn text_string(&self) -> Cow<'a, str>;
}

impl<'a> ElementRefExt<'a> for ElementRef<'a> {
    fn has_class(&self, class: &str) -> bool {
        self.value()
            .has_class(class, CaseSensitivity::CaseSensitive)
    }

    fn text_string(&self) -> Cow<'a, str> {
        let mut iter = self.text();
        match iter.next() {
            None => Cow::Borrowed(""),
            Some(t0) => match iter.next() {
                None => Cow::Borrowed(t0),
                Some(t1) => Cow::Owned([t0, t1].into_iter().chain(iter).collect()),
            },
        }
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use scraper::{Html, Selector};

    use super::*;

    #[test]
    fn text_string() {
        let selector = Selector::parse("p").unwrap();

        {
            let doc = Html::parse_document("<p></p>");
            let p = doc.select(&selector).next().unwrap();
            assert_matches!(p.text_string(), Cow::Borrowed(""));
        }

        {
            let doc = Html::parse_document("<p>Hello, World!</p>");
            let p = doc.select(&selector).next().unwrap();
            assert_matches!(p.text_string(), Cow::Borrowed("Hello, World!"));
        }

        {
            let doc = Html::parse_document("<p>Hello, <strong>World</strong>!</p>");
            let p = doc.select(&selector).next().unwrap();
            assert_matches!(p.text_string(), Cow::Owned(x) if x == "Hello, World!");
        }
    }
}
