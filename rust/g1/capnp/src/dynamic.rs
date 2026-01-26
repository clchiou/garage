use capnp::dynamic_struct;
use capnp::introspect::{Type, TypeVariant};
use capnp::message::{self, ReaderSegments};
use capnp::private::layout::{PointerReader, StructReader};
use capnp::schema::StructSchema;
use capnp::traits::FromPointerReader;
use capnp::{Error, Word};

// `capnp` does not support reading a dynamic value from a message [1], so we implement it here.
// It also does not support loading schemas at runtime [2]; all schemas (`Type` values) must be
// generated at compile time (I suspect that this is part of the reason it does not support dynamic
// value reading).
//
// [1]: https://github.com/capnproto/capnproto-rust/issues/565
// [2]: https://github.com/capnproto/capnproto-rust/issues/543
pub fn get_struct<S>(
    message: &message::Reader<S>,
    type_: Type,
) -> Result<dynamic_struct::Reader<'_>, Error>
where
    S: ReaderSegments,
{
    struct GetStructReader<'a>(StructReader<'a>);

    impl<'a> FromPointerReader<'a> for GetStructReader<'a> {
        fn get_from_pointer(
            reader: &PointerReader<'a>,
            default: Option<&'a [Word]>,
        ) -> Result<Self, Error> {
            reader.get_struct(default).map(Self)
        }
    }

    let TypeVariant::Struct(raw) = type_.which() else {
        panic!("expect struct type: {type_:?}");
    };

    Ok(dynamic_struct::Reader::new(
        message.get_root::<GetStructReader>()?.0,
        StructSchema::new(raw),
    ))
}
