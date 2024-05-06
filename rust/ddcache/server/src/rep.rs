use std::sync::OnceLock;

use bytes::Bytes;
use capnp::message;
use capnp::serialize;

use g1_zmq::envelope::Frame;

use ddcache_rpc::{
    BlobEndpoint, BlobMetadata, BlobRequest, Response, ResponseBuilder, Timestamp, Token,
};

pub(crate) fn read_response(
    metadata: Option<Bytes>,
    size: usize,
    expire_at: Option<Timestamp>,
    endpoint: BlobEndpoint,
    token: Token,
) -> Frame {
    encode(Response::Read {
        metadata: BlobMetadata {
            metadata,
            size,
            expire_at,
        },
        blob: BlobRequest { endpoint, token },
    })
}

pub(crate) fn read_metadata_response(
    metadata: Option<Bytes>,
    size: usize,
    expire_at: Option<Timestamp>,
) -> Frame {
    encode(Response::ReadMetadata {
        metadata: BlobMetadata {
            metadata,
            size,
            expire_at,
        },
    })
}

pub(crate) fn write_response(endpoint: BlobEndpoint, token: Token) -> Frame {
    encode(Response::Write {
        blob: BlobRequest { endpoint, token },
    })
}

pub(crate) fn write_metadata_response(
    metadata: Option<Bytes>,
    size: usize,
    expire_at: Option<Timestamp>,
) -> Frame {
    encode(Response::WriteMetadata {
        metadata: BlobMetadata {
            metadata,
            size,
            expire_at,
        },
    })
}

pub(crate) fn remove_response(
    metadata: Option<Bytes>,
    size: usize,
    expire_at: Option<Timestamp>,
) -> Frame {
    encode(Response::Remove {
        metadata: BlobMetadata {
            metadata,
            size,
            expire_at,
        },
    })
}

fn encode(response: Response) -> Frame {
    Vec::<u8>::from(response).into()
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

make_const_response!(ok_none_response => /* Do nothing. */);

make_const_response!(cancel_response => .init_ok().set_cancel(()));

make_const_response!(server_error => .init_err().set_server(()));

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
