use std::sync::OnceLock;

use bytes::Bytes;
use capnp::message;
use capnp::serialize;

use g1_zmq::envelope::Frame;

use ddcache_rpc::{BlobEndpoint, ResponseBuilder, Token};

pub(crate) fn read_response(
    metadata: Option<Bytes>,
    size: u64,
    endpoint: BlobEndpoint,
    token: Token,
) -> Frame {
    let mut message = message::Builder::new_default();
    let mut read = message.init_root::<ResponseBuilder>().init_ok().init_read();
    if let Some(metadata) = metadata {
        read.set_metadata(&metadata);
    }
    read.set_size(size.try_into().unwrap());
    read.reborrow().init_endpoint().set(endpoint);
    read.set_token(token);
    serialize::write_message_to_words(&message).into()
}

pub(crate) fn read_metadata_response(metadata: Option<Bytes>, size: u64) -> Frame {
    let mut message = message::Builder::new_default();
    let mut read = message
        .init_root::<ResponseBuilder>()
        .init_ok()
        .init_read_metadata();
    if let Some(metadata) = metadata {
        read.set_metadata(&metadata);
    }
    read.set_size(size.try_into().unwrap());
    serialize::write_message_to_words(&message).into()
}

pub(crate) fn write_response(endpoint: BlobEndpoint, token: Token) -> Frame {
    let mut message = message::Builder::new_default();
    let mut write = message
        .init_root::<ResponseBuilder>()
        .init_ok()
        .init_write();
    write.reborrow().init_endpoint().set(endpoint);
    write.set_token(token);
    serialize::write_message_to_words(&message).into()
}

macro_rules! make_const_response {
    ($name:ident => $($init:tt)*) => {
        pub(crate) fn $name() -> Frame {
            static ONCE: OnceLock<Vec<u8>> = OnceLock::new();
            ONCE.get_or_init(|| {
                let mut message = message::Builder::new_default();
                message.init_root::<ResponseBuilder>()$($init)*;
                serialize::write_message_to_words(&message)
            })
            .as_slice()
            .into()
        }
    };
}

make_const_response!(ping_response => .init_ok().set_ping(()));
make_const_response!(cancel_response => .init_ok().set_cancel(()));
make_const_response!(ok_none_response => /* Do nothing. */);

make_const_response!(unavailable_error => .init_err().set_unavailable(()));
make_const_response!(invalid_request_error => .init_err().set_invalid_request(()));
make_const_response!(
    max_key_size_exceeded_error =>
    .init_err().set_max_key_size_exceeded(to_u32(crate::max_key_size()))
);
make_const_response!(
    max_metadata_size_exceeded_error =>
    .init_err().set_max_metadata_size_exceeded(to_u32(crate::max_metadata_size()))
);
make_const_response!(
    max_blob_size_exceeded_error =>
    .init_err().set_max_blob_size_exceeded(to_u32(crate::max_blob_size()))
);

fn to_u32(x: &usize) -> u32 {
    (*x).try_into().unwrap()
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use capnp::Error;

    use ddcache_rpc::{ResponseOwner, ResponseResult};

    use super::*;

    #[test]
    fn test_ok_none_response() -> Result<(), Error> {
        let response = ResponseOwner::try_from(ok_none_response())?.map(ResponseResult::try_from);
        let response = unsafe { response.transpose() }?;
        assert_matches!(*response, Ok(None));
        Ok(())
    }
}
