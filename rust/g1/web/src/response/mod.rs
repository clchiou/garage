pub mod body;

use hyper::header::RETRY_AFTER;
use hyper::StatusCode;

pub type Response = hyper::Response<self::body::Body>;

pub use http::response::Builder;

pub(crate) fn shutdown() -> Response {
    Builder::new()
        .status(StatusCode::SERVICE_UNAVAILABLE)
        .header(RETRY_AFTER, 10)
        .body(body::empty())
        .expect("shutdown")
}
