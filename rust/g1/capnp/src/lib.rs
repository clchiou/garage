pub mod owner;
pub mod strict;

pub mod result_capnp {
    // TODO: Remove `clippy::needless_lifetimes` after [#522] has been fixed.
    // [#522]: https://github.com/capnproto/capnproto-rust/issues/522
    #![allow(
        clippy::extra_unused_type_parameters,
        clippy::needless_lifetimes,
        clippy::uninlined_format_args
    )]
    include!(concat!(env!("OUT_DIR"), "/g1/result_capnp.rs"));
}

use capnp::{traits::Owned, Error};

use crate::result_capnp::result;

impl<'a, T, E> TryFrom<result::Reader<'a, T, E>> for Result<Option<T::Reader<'a>>, E::Reader<'a>>
where
    T: Owned,
    E: Owned,
{
    type Error = Error;

    fn try_from(result: result::Reader<'a, T, E>) -> Result<Self, Self::Error> {
        let has_ok = result.has_ok();
        Ok(match result.which()? {
            result::Ok(ok) => Ok(has_ok.then_some(ok?)),
            result::Err(err) => Err(err?),
        })
    }
}

impl<'a, T, E> TryFrom<result::Builder<'a, T, E>> for Result<Option<T::Builder<'a>>, E::Builder<'a>>
where
    T: Owned,
    E: Owned,
{
    type Error = Error;

    fn try_from(result: result::Builder<'a, T, E>) -> Result<Self, Self::Error> {
        let has_ok = result.has_ok();
        Ok(match result.which()? {
            result::Ok(ok) => Ok(has_ok.then_some(ok?)),
            result::Err(err) => Err(err?),
        })
    }
}

#[cfg(test)]
mod tests {
    use capnp::data;
    use capnp::message;
    use capnp::serialize;

    use super::*;

    type Reader<'a> = result::Reader<'a, data::Owned, data::Owned>;
    type Builder<'a> = result::Builder<'a, data::Owned, data::Owned>;

    type R<'a> = Result<Option<data::Reader<'a>>, data::Reader<'a>>;
    type B<'a> = Result<Option<data::Builder<'a>>, data::Builder<'a>>;

    #[test]
    fn conversion() -> Result<(), Error> {
        let mut x = *b"foo";
        let x = x.as_mut_slice();

        let mut message = message::Builder::new_default();
        let mut result = message.init_root::<Builder>();
        assert_eq!(R::try_from(result.reborrow_as_reader())?, Ok(None));
        assert_eq!(B::try_from(result.reborrow())?, Ok(None));

        result.set_ok(&*x)?;
        assert_eq!(R::try_from(result.reborrow_as_reader())?, Ok(Some(&*x)));
        assert_eq!(B::try_from(result.reborrow())?, Ok(Some(&mut *x)));

        let mut message = message::Builder::new_default();
        let mut result = message.init_root::<Builder>();
        result.set_err(&*x)?;
        assert_eq!(R::try_from(result.reborrow_as_reader())?, Err(&*x));
        assert_eq!(B::try_from(result.reborrow())?, Err(&mut *x));

        Ok(())
    }

    #[test]
    fn serde() -> Result<(), Error> {
        let buffer = {
            let mut message = message::Builder::new_default();
            let mut result = message.init_root::<Builder>();
            result.set_ok(b"foo".as_slice())?;
            serialize::write_message_to_words(&message)
        };

        let message =
            serialize::read_message_from_flat_slice(&mut buffer.as_slice(), Default::default())?;
        let result = message.get_root::<Reader>()?;
        assert_eq!(R::try_from(result.reborrow())?, Ok(Some(b"foo".as_slice())));

        Ok(())
    }
}
