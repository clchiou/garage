use std::convert::Infallible;
use std::future::Future;

use hyper::service;

use crate::request::Request;
use crate::response::Response;

pub trait Handler {
    type Error: Into<Response>;
    type Future: Future<Output = Result<Response, Self::Error>>;

    fn call(&self, request: Request) -> Self::Future;

    fn into_service(self) -> HandlerService<Self>
    where
        Self: Sized,
    {
        HandlerService::new(self)
    }
}

impl<F, E, Fut> Handler for F
where
    F: Fn(Request) -> Fut,
    E: Into<Response>,
    Fut: Future<Output = Result<Response, E>>,
{
    type Error = E;
    type Future = Fut;

    fn call(&self, request: Request) -> Self::Future {
        self(request)
    }
}

#[derive(Clone, Debug)]
pub struct HandlerService<H>(H);

impl<H> HandlerService<H> {
    pub fn new(handler: H) -> Self {
        Self(handler)
    }
}

impl<H> service::Service<Request> for HandlerService<H>
where
    H: Handler,
{
    type Response = Response;
    type Error = Infallible;
    type Future = impl Future<Output = Result<Self::Response, Self::Error>>;

    fn call(&self, request: Request) -> Self::Future {
        let handle = self.0.call(request);
        async move { Ok(handle.await.unwrap_or_else(|error| error.into())) }
    }
}
