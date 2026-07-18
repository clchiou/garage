use std::iter::TrustedLen;
use std::ops::{Residual, Try};

use capnp::message::{ReaderSegments, TypedBuilder, TypedReader};
use capnp::struct_list;
use capnp::text;
use capnp::text_list;
use capnp::traits::{IntoInternalStructReader, Owned, OwnedStruct, SetterInput};

use g1_base::convert::MustInto;
use g1_base::iter::IteratorExt as _;

pub trait IteratorExt: Iterator {
    fn collect_list<L>(self) -> L
    where
        Self: Sized,
        L: ListFromIterator<Self::Item>;

    fn try_collect_list<L>(&mut self) -> <<Self::Item as Try>::Residual as Residual<L>>::TryType
    where
        Self: Sized,
        Self::Item: Try,
        <Self::Item as Try>::Residual: Residual<L>,
        <Self::Item as Try>::Residual: Residual<Vec<<Self::Item as Try>::Output>>,
        L: ListFromIterator<<Self::Item as Try>::Output>,
    {
        Try::from_output(ListFromIterator::from_iter(self.try_collect::<Vec<_>>()?))
    }
}

impl<I> IteratorExt for I
where
    I: Iterator,
{
    default fn collect_list<L>(self) -> L
    where
        Self: Sized,
        L: ListFromIterator<Self::Item>,
    {
        ListFromIterator::from_iter(self.collect::<Vec<_>>())
    }
}

impl<I> IteratorExt for I
where
    I: Iterator + TrustedLen,
{
    fn collect_list<L>(self) -> L
    where
        Self: Sized,
        L: ListFromIterator<Self::Item>,
    {
        ListFromIterator::from_iter(self)
    }
}

// We define our own version of `FromIterator` because capnp list builder requires buffer
// preallocation, which makes it incompatible with the stdlib's `FromIterator`.
pub trait ListFromIterator<T>: Sized {
    fn from_iter<I>(iter: I) -> Self
    where
        I: IntoIterator<Item = T>,
        <I as IntoIterator>::IntoIter: TrustedLen;
}

impl<T> ListFromIterator<T> for TypedBuilder<text_list::Owned>
where
    T: SetterInput<text::Owned>,
{
    fn from_iter<I>(iter: I) -> Self
    where
        I: IntoIterator<Item = T>,
        <I as IntoIterator>::IntoIter: TrustedLen,
    {
        let iter = iter.into_iter();
        let mut builder = Self::new_default();
        let mut text_list = builder.initn_root(iter.trusted_len().must_into());
        for (i, text) in iter.enumerate() {
            text_list.set(i.must_into(), text);
        }
        builder
    }
}

// NOTE: It calls `set_with_caveats`.
impl<S, T> ListFromIterator<TypedReader<S, T>> for TypedBuilder<struct_list::Owned<T>>
where
    S: ReaderSegments,
    T: Owned,
    for<'a> T: OwnedStruct<Reader<'a> = <T as Owned>::Reader<'a>>,
    for<'a> <T as Owned>::Reader<'a>: IntoInternalStructReader<'a>,
{
    fn from_iter<I>(iter: I) -> Self
    where
        I: IntoIterator<Item = TypedReader<S, T>>,
        <I as IntoIterator>::IntoIter: TrustedLen,
    {
        let iter = iter.into_iter();
        let mut builder = Self::new_default();
        let mut struct_list = builder.initn_root(iter.trusted_len().must_into());
        for (i, element) in iter.enumerate() {
            struct_list
                .set_with_caveats(i.must_into(), element.get().expect("reader"))
                .expect("set_with_caveats");
        }
        builder
    }
}
