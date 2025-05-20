use std::fmt;
use std::ops::Deref;
use std::pin::Pin;

use capnp::Error;
use capnp::message;
use capnp::serialize::{self, BufferSegments};
use capnp::traits::FromPointerReader;

use g1_base::ops::Deref;

type Message = message::Reader<BufferSegments<&'static [u8]>>;

// TODO: We implement `AsRef` and `Deref` for `Owner`.  There is a crucial difference in our
// implementation compared to `g1_base::define_owner`: We do not "downgrade" the lifetime of
// `reader` from `'static` to `'a`.  How can we prove that this no-downgrade is safe?
#[derive(Deref)]
pub struct Owner<B, T> {
    buffer: Pin<B>,
    message: Pin<Box<Message>>,
    #[deref(target)]
    reader: T,
}

impl<B, T> AsRef<T> for Owner<B, T> {
    fn as_ref(&self) -> &T {
        &self.reader
    }
}

// Implement `Send` for `Owner` because capnp reader types are not `Send`.
// TODO: Can we prove that this is actually safe?
unsafe impl<B, T> Send for Owner<B, T> {}

impl<B, T> fmt::Debug for Owner<B, T>
where
    B: fmt::Debug,
    T: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Owner")
            .field("buffer", &self.buffer)
            .field("message", &"_")
            .field("reader", &self.reader)
            .finish()
    }
}

// TODO: Somehow, Rust forbids me from implementing `TryFrom<B> for Owner<B, T>`.
impl<B, T> Owner<B, T>
where
    B: Deref<Target = [u8]>,
    T: FromPointerReader<'static>,
{
    pub fn try_from(buffer: B) -> Result<Self, Error> {
        let buffer = Pin::new(buffer);

        let slice: *const [u8] = &*buffer;
        let message = Box::pin(serialize::read_message_from_flat_slice(
            &mut unsafe { &*slice },
            Default::default(),
        )?);

        let message_ptr: *const Message = &*message;
        let reader = unsafe { &*message_ptr }.get_root::<T>()?;

        Ok(Self {
            buffer,
            message,
            reader,
        })
    }
}

impl<B, T> Owner<B, T>
where
    B: Deref<Target = [u8]>,
{
    pub fn into_buffer(self) -> B {
        let Self {
            buffer,
            message,
            reader,
        } = self;
        drop(reader);
        drop(message);
        Pin::into_inner(buffer)
    }
}

impl<B, T> Owner<B, T> {
    pub fn map<F, U>(self, f: F) -> Owner<B, U>
    where
        F: FnOnce(T) -> U,
    {
        Owner {
            buffer: self.buffer,
            message: self.message,
            reader: f(self.reader),
        }
    }
}

impl<B, T> Owner<B, Option<T>> {
    pub fn transpose(self) -> Option<Owner<B, T>> {
        Some(Owner {
            buffer: self.buffer,
            message: self.message,
            reader: self.reader?,
        })
    }
}

impl<B, T, E> Owner<B, Result<T, E>> {
    /// Converts an owner-of-result into a result-of-owner.
    ///
    /// # Safety
    ///
    /// It is unsafe because `E` may borrow from the buffer, which is dropped.
    pub unsafe fn transpose(self) -> Result<Owner<B, T>, E> {
        Ok(Owner {
            buffer: self.buffer,
            message: self.message,
            reader: self.reader?,
        })
    }

    pub fn unzip(self) -> Result<Owner<B, T>, Owner<B, E>> {
        match self.reader {
            Ok(reader) => Ok(Owner {
                buffer: self.buffer,
                message: self.message,
                reader,
            }),
            Err(error) => Err(Owner {
                buffer: self.buffer,
                message: self.message,
                reader: error,
            }),
        }
    }
}

#[cfg(test)]
mod tests {
    use capnp::data;

    use crate::result_capnp::result;

    use super::*;

    type Reader<'a> = result::Reader<'a, data::Owned, data::Owned>;
    type Builder<'a> = result::Builder<'a, data::Owned, data::Owned>;

    type R<'a> = Result<Option<data::Reader<'a>>, data::Reader<'a>>;

    #[test]
    fn owner() -> Result<(), Error> {
        let buffer = {
            let mut message = message::Builder::new_default();
            let mut result = message.init_root::<Builder>();
            result.set_ok(b"foo".as_slice())?;
            serialize::write_message_to_words(&message)
        };

        let owner = Owner::<_, Reader>::try_from(buffer)?;
        let owner = owner.map(R::try_from);
        // It is safe to `transpose` because `E` is `capnp::Error`.
        let owner = unsafe { owner.transpose() }?;
        assert_eq!(owner.as_ref(), &Ok(Some(b"foo".as_slice())));
        assert_eq!(&*owner, &Ok(Some(b"foo".as_slice())));

        Ok(())
    }
}
