#![feature(impl_trait_in_assoc_type)]
#![feature(trait_alias)]

pub mod handler;
pub mod request;
pub mod response;
pub mod server;
pub mod service;

pub use crate::handler::{Handler, HandlerService};
pub use crate::request::Request;
pub use crate::response::Response;
pub use crate::response::body::Body;
pub use crate::server::{Server, ServerGuard};
pub use crate::service::Service;
