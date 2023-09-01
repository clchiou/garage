//! Self-Referential Container
//!
//! The container possesses a buffer and a borrower of the buffer.
//!
//! NOTE: The container is entirely implemented via the macro `define_owner!` because we are unable
//! to implement the container for a generic borrower type `T`.  This limitation arises from the
//! fact that a generic parameter `T` cannot be bounded by a lifetime parameter (e.g., `T<'a>`).
//! However, the container requires the ability to "downgrade" the lifetime of the borrower from
//! `'static` to `'a`.

use std::pin::Pin;

/// Creates a container type for the `$borrower` type.
///
/// NOTE: Although `$borrower` is a type, the macro captures it as an identifier instead of a type
/// or a path.  This limitation exists because the macro needs to manipulate the `$borrower`.
//
// TODO: We cannot use the declarative macros 2.0 because their hygiene rules are the opposite of
// the macros 1.0 rules.  Currently, macros 2.0 only support definition-site hygiene, which means
// we are unable to "export" definitions from the macro body.
#[macro_export]
macro_rules! define_owner {
    ($(#[$meta:meta])* $vis:vis $owner:ident for $borrower:ident) => {
        $(#[$meta])*
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

        impl<Buffer> $crate::owner::_Owner<Buffer> for $owner<Buffer> {
            type Borrower = $borrower<'static>;

            fn into_parts(self) -> (::std::pin::Pin<Buffer>, Self::Borrower) {
                (self.buffer, self.borrower)
            }

            fn from_parts(buffer: ::std::pin::Pin<Buffer>, borrower: Self::Borrower) -> Self {
                Self { buffer, borrower }
            }
        }
    };
}

/// Implements `TryFrom` for conversion between two container types.
#[macro_export]
macro_rules! impl_owner_try_from {
    ($($from_owner:tt)::* for $($to_owner:tt)::*) => {
        impl<Buffer, T, U>
            ::std::convert::TryFrom<$($from_owner)::*<Buffer>> for $($to_owner)::*<Buffer>
        where
            $($from_owner)::*<Buffer>: $crate::owner::_Owner<Buffer, Borrower = T>,
            $($to_owner)::*<Buffer>: $crate::owner::_Owner<Buffer, Borrower = U>,
            U: ::std::convert::TryFrom<T>,
        {
            type Error = <U as ::std::convert::TryFrom<T>>::Error;

            fn try_from(owner: $($from_owner)::*<Buffer>) -> Result<Self, Self::Error> {
                use $crate::owner::_Owner;

                let (buffer, borrower) = owner.into_parts();
                Ok(Self::from_parts(buffer, borrower.try_into()?))
            }
        }
    };
}

/// Private helper trait for container `TryFrom` implementations.
pub trait _Owner<Buffer> {
    type Borrower;

    fn into_parts(self) -> (Pin<Buffer>, Self::Borrower);

    fn from_parts(buffer: Pin<Buffer>, borrower: Self::Borrower) -> Self;
}

#[cfg(test)]
mod tests {
    #[derive(Debug, Eq, PartialEq)]
    struct Bytes<'a>(&'a [u8]);

    #[derive(Debug, Eq, PartialEq)]
    struct HalfBytes<'a>(&'a [u8]);

    impl<'a> TryFrom<&'a [u8]> for Bytes<'a> {
        type Error = ();

        fn try_from(bytes: &'a [u8]) -> Result<Self, Self::Error> {
            Ok(Bytes(bytes))
        }
    }

    impl<'a> TryFrom<&'a [u8]> for HalfBytes<'a> {
        type Error = ();

        fn try_from(bytes: &'a [u8]) -> Result<Self, Self::Error> {
            Ok(HalfBytes(&bytes[..bytes.len() / 2]))
        }
    }

    impl<'a> TryFrom<Bytes<'a>> for HalfBytes<'a> {
        type Error = ();

        fn try_from(Bytes(bytes): Bytes<'a>) -> Result<Self, Self::Error> {
            Ok(HalfBytes(&bytes[..bytes.len() / 2]))
        }
    }

    define_owner!(OwnedBytes for Bytes);

    define_owner!(OwnedHalfBytes for HalfBytes);

    mod foo {
        mod bar {
            impl_owner_try_from!(super::super::OwnedBytes for super::super::OwnedHalfBytes);
        }
    }

    #[test]
    fn owner() {
        let x = OwnedBytes::try_from(vec![0, 1, 2]).unwrap();
        assert_eq!(OwnedBytes::as_slice(&x), &[0, 1, 2]);
        assert_eq!(x.deref(), &Bytes(&[0, 1, 2]));

        let x: OwnedHalfBytes<_> = x.try_into().unwrap();
        assert_eq!(OwnedHalfBytes::as_slice(&x), &[0, 1, 2]);
        assert_eq!(x.deref(), &HalfBytes(&[0]));

        let x = OwnedHalfBytes::try_from(vec![0, 1, 2, 3]).unwrap();
        assert_eq!(OwnedHalfBytes::as_slice(&x), &[0, 1, 2, 3]);
        assert_eq!(x.deref(), &HalfBytes(&[0, 1]));
    }
}
