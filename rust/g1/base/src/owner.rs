//! Self-Referential Container
//!
//! The container possesses a buffer and a borrower of the buffer.
//!
//! NOTE: The container is entirely implemented via the macro `def_owner!` because we are unable to
//! implement the container for a generic borrower type `T`.  This limitation arises from the fact
//! that a generic parameter `T` cannot be bounded by a lifetime parameter (e.g., `T<'a>`).
//! However, the container requires the ability to "downgrade" the lifetime of the borrower from
//! `'static` to `'a`.

#[macro_export]
macro_rules! def_owner {
    ($vis:vis $owner:ident for $borrower:ident) => {
        $vis struct $owner<Buffer> {
            buffer: ::std::pin::Pin<Buffer>,
            borrower: $borrower<'static>,
        }

        /// Converts a buffer into an owner value.
        ///
        /// NOTE: Due to [rust-lang/rust#50133][#50133], we are unable to implement
        /// `TryFrom<Buffer>` for the owner, even with the use of `feature(min_specialization)`.
        ///
        /// [#50133]: https://github.com/rust-lang/rust/issues/50133
        impl<Buffer> $owner<Buffer>
        where
            Buffer: ::std::ops::Deref<Target = [u8]>,
            // This trait bound ensures that `Error` never borrows from `Buffer` because `Buffer`
            // is deallocated on error.
            for<'a> <$borrower<'a> as ::std::convert::TryFrom<&'a [u8]>>::Error: 'static,
        {
            $vis fn try_from(
                buffer: Buffer,
            ) -> Result<Self, <$borrower<'static> as ::std::convert::TryFrom<&'static [u8]>>::Error>
            {
                let buffer = ::std::pin::Pin::new(buffer);
                let borrowed: *const [u8] = &*buffer;
                Ok($owner {
                    buffer,
                    borrower: <$borrower>::try_from(unsafe { &*borrowed })?,
                })
            }
        }

        /// Returns a reference to the buffer.
        ///
        /// It is not a method of the owner but a function that operates on a reference to an owner
        /// value.  The reason for this is that in the future, we might be able to implement `Deref`
        /// for the owner.
        impl<Buffer> $owner<Buffer>
        where
            Buffer: ::std::ops::Deref<Target = [u8]>,
        {
            $vis fn as_slice(this: &Self) -> &[u8] {
                &this.buffer
            }
        }

        /// Returns a reference to the borrower.
        ///
        /// NOTE: We are unable to implement `Deref` for the owner because `Deref::Target` does not
        /// take a lifetime parameter.
        impl<Buffer> $owner<Buffer> {
            $vis fn deref(&self) -> &$borrower<'_> {
                &self.borrower
            }
        }
    };
}

#[cfg(test)]
mod tests {
    #[derive(Debug, Eq, PartialEq)]
    struct Bytes<'a>(&'a [u8]);

    impl<'a> TryFrom<&'a [u8]> for Bytes<'a> {
        type Error = ();

        fn try_from(bytes: &'a [u8]) -> Result<Self, Self::Error> {
            Ok(Bytes(bytes))
        }
    }

    def_owner!(OwnedBytes for Bytes);

    #[test]
    fn owner() {
        let x = OwnedBytes::try_from(vec![0, 1, 2]).unwrap();
        assert_eq!(OwnedBytes::as_slice(&x), &[0, 1, 2]);
        assert_eq!(x.deref(), &Bytes(&[0, 1, 2]));
    }
}
