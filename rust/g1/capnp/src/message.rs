use capnp::Error;
use capnp::message::{Builder, HeapAllocator, Reader, ReaderSegments, TypedBuilder};
use capnp::private::units::BYTES_PER_WORD;
use capnp::traits::Owned;

pub trait BuilderExt: Sized {
    /// Allocates and builds the canonical form of the message.
    ///
    /// `Builder::set_root_canonical` requires the caller to allocate the space, or it panics if
    /// the message is larger than the first segment.
    ///
    /// `Reader::canonicalize` performs the allocation, but it returns a `Vec<Word>` and excludes
    /// the segment table, making it unsuitable for serialization.
    fn new_canonical<S, T>(reader: &Reader<S>) -> Result<Self, Error>
    where
        S: ReaderSegments,
        T: Owned;

    fn into_canonical<T>(self) -> Result<Self, Error>
    where
        T: Owned;
}

pub trait TypedBuilderExt<T>: Sized
where
    T: Owned,
{
    fn new_canonical<S>(reader: &Reader<S>) -> Result<Self, Error>
    where
        S: ReaderSegments;

    fn into_canonical(self) -> Result<Self, Error>;
}

impl BuilderExt for Builder<HeapAllocator> {
    fn new_canonical<S, T>(reader: &Reader<S>) -> Result<Self, Error>
    where
        S: ReaderSegments,
        T: Owned,
    {
        // TODO: Work around [bug] where `Reader::size_in_words` returns size in bytes instead of
        // words.  Remove after upgrading capnp to v0.23.1.
        // [bug]: https://github.com/capnproto/capnproto-rust/issues/603
        let size = u32::try_from(reader.size_in_words() / BYTES_PER_WORD).expect("u32");
        let mut builder = Self::new(HeapAllocator::new().first_segment_words(size + 1));
        builder.set_root_canonical(reader.get_root::<T::Reader<'_>>()?)?;
        assert_eq!(builder.get_segments_for_output().len(), 1);
        Ok(builder)
    }

    fn into_canonical<T>(self) -> Result<Self, Error>
    where
        T: Owned,
    {
        Self::new_canonical::<_, T>(&self.into_reader())
    }
}

impl<T> TypedBuilderExt<T> for TypedBuilder<T>
where
    T: Owned,
{
    fn new_canonical<S>(reader: &Reader<S>) -> Result<Self, Error>
    where
        S: ReaderSegments,
    {
        Builder::new_canonical::<_, T>(reader).map(Self::new)
    }

    fn into_canonical(self) -> Result<Self, Error> {
        Self::new_canonical(&self.into_reader().into_inner())
    }
}

#[cfg(test)]
mod tests {
    use capnp::data;

    use super::*;

    // TODO: Currently, our code relies on this [bug].  Remove this after upgrading to v0.23.1.
    // [bug]: https://github.com/capnproto/capnproto-rust/issues/603
    #[test]
    fn reader_size_in_words() {
        let mut builder = Builder::new_default();
        builder
            .set_root::<data::Owned>(b"foobar".as_slice())
            .unwrap();
        assert_eq!(builder.into_reader().size_in_words(), 16);
    }
}
