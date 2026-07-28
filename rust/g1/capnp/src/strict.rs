//! Provide a "strict" version of getters that crashes on `capnp::Error`.

use capnp::message::{Allocator, ReaderSegments, TypedBuilder, TypedReader};
use capnp::struct_list;
use capnp::text;
use capnp::text_list;
use capnp::traits::{IntoInternalStructReader, ListIter, Owned, OwnedStruct};

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
        self.iter()
    }
}

impl<'a> TextList<'a> {
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn len(&self) -> u32 {
        self.0.len()
    }

    pub fn iter(self) -> TextListIter<'a> {
        TextListIter(self.0.iter())
    }

    pub fn get(&self, index: u32) -> &'a str {
        self.0.get(index).expect("get").must_to_str()
    }

    pub fn try_get(&self, index: u32) -> Option<&'a str> {
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

pub trait StructListBuilderExt<T>
where
    T: OwnedStruct,
{
    fn must_set_with_caveats<'b>(&mut self, index: u32, value: T::Reader<'b>)
    where
        T::Reader<'b>: IntoInternalStructReader<'b>;
}

impl<'a, T> StructListBuilderExt<T> for struct_list::Builder<'a, T>
where
    T: OwnedStruct,
{
    fn must_set_with_caveats<'b>(&mut self, index: u32, value: T::Reader<'b>)
    where
        T::Reader<'b>: IntoInternalStructReader<'b>,
    {
        self.set_with_caveats(index, value)
            .expect("set_with_caveats")
    }
}

pub trait TypedReaderExt<T>
where
    T: Owned,
{
    fn root(&self) -> T::Reader<'_>;
}

impl<S, T> TypedReaderExt<T> for TypedReader<S, T>
where
    S: ReaderSegments,
    T: Owned,
{
    fn root(&self) -> T::Reader<'_> {
        self.get().expect("root")
    }
}

pub trait TypedBuilderExt<T>
where
    T: Owned,
{
    fn root(&mut self) -> T::Builder<'_>;

    fn root_as_reader(&self) -> T::Reader<'_>;

    fn must_set_root(&mut self, value: T::Reader<'_>);
}

impl<T, A> TypedBuilderExt<T> for TypedBuilder<T, A>
where
    T: Owned,
    A: Allocator,
{
    fn root(&mut self) -> T::Builder<'_> {
        self.get_root().expect("root")
    }

    fn root_as_reader(&self) -> T::Reader<'_> {
        self.get_root_as_reader().expect("root")
    }

    fn must_set_root(&mut self, value: T::Reader<'_>) {
        self.set_root(value).expect("root")
    }
}
