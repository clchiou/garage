#![feature(iter_next_chunk)]
#![cfg_attr(test, feature(assert_matches))]

use std::borrow::Cow;

use scraper::element_ref;
use scraper::html;
use scraper::{CaseSensitivity, ElementRef, Html, Selector};

#[macro_export]
macro_rules! lazy_selector {
    ($selectors:literal $(,)?) => {{
        static SELECTOR: $crate::private::LazyLock<$crate::private::Selector> =
            $crate::private::LazyLock::new(|| {
                $crate::private::Selector::parse($selectors).expect("selector")
            });
        &SELECTOR
    }};
}

pub mod private {
    pub use scraper::Selector;
    pub use std::sync::LazyLock;
}

// Unlike `scraper::selectable::Selectable`, this uses `&self` rather than `self`, making
// implementations for foreign types easier.
pub trait Selectable<'a> {
    type Select<'b>: Iterator<Item = ElementRef<'a>>;

    fn select<'b>(&self, selector: &'b Selector) -> Self::Select<'b>;
}

impl<'a> Selectable<'a> for &'a Html {
    type Select<'b> = html::Select<'a, 'b>;

    fn select<'b>(&self, selector: &'b Selector) -> Self::Select<'b> {
        Html::select(self, selector)
    }
}

impl<'a> Selectable<'a> for ElementRef<'a> {
    type Select<'b> = element_ref::Select<'a, 'b>;

    fn select<'b>(&self, selector: &'b Selector) -> Self::Select<'b> {
        ElementRef::select(self, selector)
    }
}

pub trait SelectExt<'a> {
    /// Expects exactly one matching element or descendant.
    fn select_unique(&self, selector: &Selector) -> Option<ElementRef<'a>>;

    /// Expects exactly `N` matching elements or descendants.
    fn select_exact<const N: usize>(&self, selector: &Selector) -> Option<[ElementRef<'a>; N]>;

    /// Expects at least one matching element or descendant.
    fn select_head(&self, selector: &Selector) -> Option<ElementRef<'a>>;

    /// Expects at least `N` matching elements or descendants.
    fn select_chunk<const N: usize>(&self, selector: &Selector) -> Option<[ElementRef<'a>; N]>;
}

impl<'a, S> SelectExt<'a> for S
where
    S: Selectable<'a>,
{
    fn select_unique(&self, selector: &Selector) -> Option<ElementRef<'a>> {
        self.select_exact::<1>(selector).map(|[e]| e)
    }

    fn select_exact<const N: usize>(&self, selector: &Selector) -> Option<[ElementRef<'a>; N]> {
        let mut select = self.select(selector);
        let chunk = select.next_chunk().ok()?;
        select.next().is_none().then_some(chunk)
    }

    fn select_head(&self, selector: &Selector) -> Option<ElementRef<'a>> {
        self.select_chunk::<1>(selector).map(|[e]| e)
    }

    fn select_chunk<const N: usize>(&self, selector: &Selector) -> Option<[ElementRef<'a>; N]> {
        self.select(selector).next_chunk().ok()
    }
}

pub trait ElementRefExt<'a> {
    fn has_class(&self, class: &str) -> bool;

    fn text_string(&self) -> Cow<'a, str>;

    fn matches(&self, selector: &Selector) -> bool;
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

    fn matches(&self, selector: &Selector) -> bool {
        selector.matches_with_scope(self, Some(*self))
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use super::*;

    // There is a subtle difference between `Html::select` and `ElementRef::select`: the latter
    // searches only descendant elements.
    #[test]
    fn descendant() {
        let doc = Html::parse_document("<html></html>");
        let root = doc.root_element();
        for selector in [
            lazy_selector!("html"),
            lazy_selector!(":root"),
            lazy_selector!(":scope"),
        ] {
            assert_eq!(doc.select(selector).next(), Some(root));
            assert_eq!(root.select(selector).next(), None);
        }
    }

    #[test]
    fn select_ext() {
        fn ids_eq<const N: usize>(es: [ElementRef<'_>; N], ids: [&str; N]) -> bool {
            es.map(|e| e.attr("id").unwrap()) == ids
        }

        let doc = Html::parse_document(
            r#"
            <div id="a" class="one"></div>
            <div id="b" class="two"></div>
            <div id="c" class="two"></div>
            "#,
        );
        let doc = &doc;

        let select_zero = lazy_selector!("div.zero");
        let select_one = lazy_selector!("div.one");
        let select_two = lazy_selector!("div.two");

        assert_matches!(doc.select_unique(select_zero), None);
        assert_matches!(doc.select_unique(select_one), Some(e) if ids_eq([e], ["a"]));
        assert_matches!(doc.select_unique(select_two), None);

        assert_matches!(doc.select_exact::<2>(select_zero), None);
        assert_matches!(doc.select_exact::<2>(select_one), None);
        assert_matches!(doc.select_exact::<2>(select_two), Some(es) if ids_eq(es, ["b", "c"]));
        assert_matches!(doc.select_exact::<3>(select_two), None);

        assert_matches!(doc.select_head(select_zero), None);
        assert_matches!(doc.select_head(select_one), Some(e) if ids_eq([e], ["a"]));
        assert_matches!(doc.select_head(select_two), Some(e) if ids_eq([e], ["b"]));

        assert_matches!(doc.select_chunk::<2>(select_zero), None);
        assert_matches!(doc.select_chunk::<2>(select_one), None);
        assert_matches!(doc.select_chunk::<2>(select_two), Some(es) if ids_eq(es, ["b", "c"]));
        assert_matches!(doc.select_chunk::<3>(select_two), None);
    }

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

    #[test]
    fn matches() {
        let doc = Html::parse_document(
            r#"
            <div class="a">
                <div class="b">
                    <div class="c"></div>
                </div>
                <div class="d"></div>
                <div class="e"></div>
            </div>
            "#,
        );
        let doc = &doc;
        let a = doc.select_unique(lazy_selector!(".a")).unwrap();
        let b = doc.select_unique(lazy_selector!(".b")).unwrap();
        let c = doc.select_unique(lazy_selector!(".c")).unwrap();
        let d = doc.select_unique(lazy_selector!(".d")).unwrap();
        let e = doc.select_unique(lazy_selector!(".e")).unwrap();

        assert_eq!(a.matches(lazy_selector!("div.a:scope")), true);
        assert_eq!(b.matches(lazy_selector!("div.b:scope")), true);
        assert_eq!(c.matches(lazy_selector!("div.c:scope")), true);
        assert_eq!(d.matches(lazy_selector!("div.d:scope")), true);
        assert_eq!(e.matches(lazy_selector!("div.e:scope")), true);

        assert_eq!(a.matches(lazy_selector!(".a, .b")), true);
        assert_eq!(a.matches(lazy_selector!("    .b")), false);

        assert_eq!(b.matches(lazy_selector!(".a   .b")), true);
        assert_eq!(b.matches(lazy_selector!(".a > .b")), true);

        assert_eq!(c.matches(lazy_selector!(".a   .c")), true);
        assert_eq!(c.matches(lazy_selector!(".a > .c")), false);

        assert_eq!(d.matches(lazy_selector!(".b ~ .d")), true);
        assert_eq!(d.matches(lazy_selector!(".b + .d")), true);

        assert_eq!(e.matches(lazy_selector!(".b ~ .e")), true);
        assert_eq!(e.matches(lazy_selector!(".b + .e")), false);
    }
}
