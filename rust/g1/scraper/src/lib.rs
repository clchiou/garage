use scraper::{CaseSensitivity, ElementRef};

pub trait ElementRefExt {
    fn has_class(&self, class: &str) -> bool;

    fn text_string(&self) -> String;
}

impl ElementRefExt for ElementRef<'_> {
    fn has_class(&self, class: &str) -> bool {
        self.value()
            .has_class(class, CaseSensitivity::CaseSensitive)
    }

    fn text_string(&self) -> String {
        self.text().collect()
    }
}
