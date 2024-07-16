use std::convert::Infallible;
use std::future::Future;
use std::net::SocketAddr;

use hyper::service;
use tracing::Instrument;

use g1_tokio::task::Cancel;

use crate::request::Request;
use crate::response;
use crate::response::Response;

// We require a service to always return an HTTP 4xx or 5xx status code in case of an error, and
// therefore, `Error` is set to `Infallible`.
pub trait Service =
    service::Service<Request, Response = Response, Error = Infallible, Future: Send>;

// Add `Clone` so that the return type becomes compatible with `Server::spawn`.
pub fn service_fn<F, Fut>(service: F) -> impl Clone + Service
where
    F: Clone + Fn(Request) -> Fut,
    Fut: Future<Output = Response> + Send,
{
    service::service_fn(move |request| {
        let serve = service(request);
        async move { Ok(serve.await) }
    })
}

#[derive(Debug)]
pub(crate) struct ServiceContainer<S> {
    cancel: Cancel,
    client: SocketAddr,
    service: S,
}

impl<S> ServiceContainer<S> {
    pub(crate) fn new(cancel: Cancel, client: SocketAddr, service: S) -> Self {
        Self {
            cancel,
            client,
            service,
        }
    }
}

// Somehow Rust does not allow implementing a trait alias.
impl<S> service::Service<Request> for ServiceContainer<S>
where
    S: Service,
{
    type Response = Response;
    type Error = Infallible;
    type Future = impl Future<Output = Result<Self::Response, Self::Error>>;

    fn call(&self, request: Request) -> Self::Future {
        // At the moment, for simplicity, we assume that service futures can be cancelled by simply
        // dropping them.
        let cancel = self.cancel.clone();
        let serve = self.service.call(request);
        async move {
            tokio::select! {
                () = cancel.wait() => Ok(response::shutdown()),
                result = serve => result,
            }
        }
        .instrument(tracing::info_span!("web/serve", client = %self.client))
    }
}
