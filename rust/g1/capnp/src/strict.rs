//! Provide a "strict" version of getters that crashes on `capnp::Error`.

use capnp::text;
use capnp::text_list;
use capnp::traits::ListIter;

pub trait TextExt<'a> {
    fn must_to_str(self) -> &'a str;
}

impl<'a> TextExt<'a> for text::Reader<'a> {
    fn must_to_str(self) -> &'a str {
        self.to_str().expect("to_str")
    }
}

// A wrapper seems more natural than a `TextListExt` trait.
pub struct TextList<'a>(text_list::Reader<'a>);

impl<'a> From<text_list::Reader<'a>> for TextList<'a> {
    fn from(list: text_list::Reader<'a>) -> Self {
        Self(list)
    }
}

impl<'a> From<TextList<'a>> for text_list::Reader<'a> {
    fn from(list: TextList<'a>) -> Self {
        list.0
    }
}

impl<'a> IntoIterator for TextList<'a> {
    type IntoIter = TextListIter<'a>;
    type Item = <Self::IntoIter as Iterator>::Item;

    fn into_iter(self) -> Self::IntoIter {
        TextListIter(self.0.into_iter())
    }
}

impl TextList<'_> {
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn len(&self) -> u32 {
        self.0.len()
    }

    pub fn get(&self, index: u32) -> &str {
        self.0.get(index).expect("get").must_to_str()
    }

    pub fn try_get(&self, index: u32) -> Option<&str> {
        self.0
            .try_get(index)
            .map(|text| text.expect("try_get").must_to_str())
    }
}

pub struct TextListIter<'a>(
    ListIter<text_list::Reader<'a>, Result<text::Reader<'a>, capnp::Error>>,
);

impl<'a> Iterator for TextListIter<'a> {
    type Item = &'a str;

    fn next(&mut self) -> Option<Self::Item> {
        self.0.next().map(|text| text.expect("next").must_to_str())
    }
}
