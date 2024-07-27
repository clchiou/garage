use std::io::Error;
use std::net::SocketAddr;

use hyper::server::conn::http1::Builder;
use hyper_util::rt::TokioIo;
use tokio::net::{TcpListener, TcpStream};

use g1_tokio::task::{Cancel, JoinGuard, JoinQueue};

use crate::service::{Service, ServiceContainer};

// For now, the `Server` stub does not do anything.
#[derive(Clone, Debug)]
pub struct Server(());

pub type ServerGuard = JoinGuard<Result<(), Error>>;

#[derive(Debug)]
struct Actor<S> {
    cancel: Cancel,
    listener: TcpListener,
    service: S,
    tasks: JoinQueue<Result<(), hyper::Error>>,
}

impl Server {
    pub fn spawn<S>(listener: TcpListener, service: S) -> (Self, ServerGuard)
    where
        S: Clone + Send + Service + 'static,
    {
        (
            Self(()),
            JoinGuard::spawn(move |cancel| Actor::new(cancel, listener, service).run()),
        )
    }
}

impl<S> Actor<S>
where
    S: Clone + Send + Service + 'static,
{
    fn new(cancel: Cancel, listener: TcpListener, service: S) -> Self {
        Self {
            cancel: cancel.clone(),
            listener,
            service,
            tasks: JoinQueue::with_cancel(cancel),
        }
    }

    async fn run(self) -> Result<(), Error> {
        loop {
            tokio::select! {
                () = self.cancel.wait() => break,

                accept = self.listener.accept() => {
                    self.accept(accept?);
                }

                guard = self.tasks.join_next() => {
                    let Some(guard) = guard else { break };
                    self.handle_task(guard);
                }
            }
        }

        self.tasks.cancel();
        while let Some(guard) = self.tasks.join_next().await {
            self.handle_task(guard);
        }

        Ok(())
    }

    fn accept(&self, (stream, endpoint): (TcpStream, SocketAddr)) {
        tracing::debug!(accept = %endpoint);
        self.tasks
            .push(JoinGuard::spawn(move |cancel| {
                // TODO: Consider supporting both HTTP/1 and HTTP/2.
                Builder::new().serve_connection(
                    TokioIo::new(stream),
                    ServiceContainer::new(cancel, endpoint, self.service.clone()),
                )
            }))
            .expect("service task");
    }

    fn handle_task(&self, mut guard: JoinGuard<Result<(), hyper::Error>>) {
        match guard.take_result() {
            Ok(Ok(())) => {}
            Ok(Err(error)) => tracing::warn!(%error, "service"),
            Err(error) => tracing::warn!(%error, "service task"),
        }
    }
}
