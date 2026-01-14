use capnp::Error;
use capnp::message::{Builder, HeapAllocator, Reader, ReaderSegments, TypedBuilder};
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
        let size = u32::try_from(reader.size_in_words()).expect("u32");
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
