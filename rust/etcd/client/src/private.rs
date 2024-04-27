use serde::{Deserialize, Serialize};
use snafu::prelude::*;

use crate::response::StreamResponse;
use crate::{DecodeSnafu, Error};

pub trait Request: Serialize {
    const ENDPOINT: &'static str;

    type Response: for<'a> Deserialize<'a>;

    fn decode(response: &[u8]) -> Result<Self::Response, Error> {
        serde_json::from_slice(response).context(DecodeSnafu)
    }

    fn encode(&self) -> Vec<u8> {
        serde_json::to_vec(self).unwrap()
    }
}

pub trait StreamRequest: Request {
    fn stream_decode(response: &[u8]) -> Result<Self::Response, Error> {
        match serde_json::from_slice::<StreamResponse<Self::Response>>(response)
            .context(DecodeSnafu)?
        {
            StreamResponse::result(response) => Ok(response),
            StreamResponse::error(status) => Err(Error::Stream { status }),
        }
    }
}
