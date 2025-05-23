use std::collections::{HashMap, VecDeque, hash_map::Entry};
use std::fmt;
use std::hash::Hash;
use std::io::{Error, ErrorKind};
use std::time::Duration;

use futures::{
    future::OptionFuture,
    sink::{Sink, SinkExt},
    stream::{Stream, StreamExt},
};
use tokio::{
    sync::{mpsc, oneshot},
    time::{self, Instant},
};

use g1_tokio::{
    sync::mpmc,
    task::{Cancel, JoinGuard},
};

//
// Implementer's Notes: There is an alternative design that does not employ an actor and instead
// moves all `Stream::try_next` calls to the `request` and `accept` methods.  I am not sure which
// design is better.  For now, we employ the actor-based design.
//

g1_param::define!(request_queue_size: usize = 64);
g1_param::define!(accept_queue_size: usize = 64);
g1_param::define!(response_queue_size: usize = 64);

g1_param::define!(
    request_timeout: Duration = Duration::from_secs(2);
    parse = g1_param::parse::duration;
);

pub mod error {
    use snafu::prelude::*;

    #[derive(Clone, Debug, Eq, PartialEq, Snafu)]
    pub enum Error {
        #[snafu(display("request conflict: {endpoint}"))]
        RequestConflict { endpoint: String },
        #[snafu(display("request timeout"))]
        RequestTimeout,
        #[snafu(display("reqrep was shut down"))]
        Shutdown,
    }
}

pub trait Message: Send {
    type Endpoint: Clone + fmt::Debug + Eq + Hash + PartialEq + Send;

    fn endpoint(&self) -> &Self::Endpoint;
}

impl<E, P> Message for (E, P)
where
    E: Clone + fmt::Debug + Eq + Hash + PartialEq + Send,
    P: Send,
{
    type Endpoint = E;

    fn endpoint(&self) -> &Self::Endpoint {
        &self.0
    }
}

type ResultRecv<T> = oneshot::Receiver<Result<T, Error>>;
type ResultSend<T> = oneshot::Sender<Result<T, Error>>;

// M: Incoming message type.
// N: Outgoing message type.
// E: Endpoint type.
#[derive(Debug)]
pub struct ReqRep<M, N, E> {
    request_send: mpsc::Sender<(N, ResultSend<M>)>,

    accept_recv: mpmc::Receiver<(M, ResultRecv<()>)>,
    response_send: mpsc::Sender<Result<N, E>>,
}

pub type ReqRepGuard = JoinGuard<Result<(), Error>>;

#[derive(Debug)]
pub struct Sender<N, E> {
    response_send: mpsc::Sender<Result<N, E>>,
    result_recv: ResultRecv<()>,
    // We use the `endpoint` field to track whether `Sender::send` is called.
    endpoint: Option<E>,
}

#[derive(Debug)]
struct Actor<M, N, E, I, O> {
    cancel: Cancel,

    incoming: I,
    outgoing: O,

    request_recv: mpsc::Receiver<(N, ResultSend<M>)>,
    request_timeout: Duration,
    // For now, we can use `VecDeque` because `request_timeout` is fixed.
    request_deadlines: VecDeque<(Instant, E)>,

    accept_send: mpmc::Sender<(M, ResultRecv<()>)>,
    response_recv: mpsc::Receiver<Result<N, E>>,

    reqrep: HashMap<E, State<M>>,
}

#[derive(Debug)]
enum State<M> {
    Request(ResultSend<M>),
    Response(ResultSend<()>),
}

impl<M, N, E> Clone for ReqRep<M, N, E> {
    fn clone(&self) -> Self {
        Self {
            request_send: self.request_send.clone(),
            accept_recv: self.accept_recv.clone(),
            response_send: self.response_send.clone(),
        }
    }
}

impl<M, N, E> ReqRep<M, N, E> {
    pub fn spawn<I, O>(incoming: I, outgoing: O) -> (Self, ReqRepGuard)
    where
        M: Message<Endpoint = E> + 'static,
        N: Message<Endpoint = E> + 'static,
        E: Clone + fmt::Debug + Eq + Hash + PartialEq + Send + 'static,
        I: Stream<Item = Result<M, Error>> + Send + Unpin + 'static,
        O: Sink<N, Error = Error> + Send + Unpin + 'static,
    {
        let (request_send, request_recv) = mpsc::channel(*request_queue_size());
        let (accept_send, accept_recv) = mpmc::channel(*accept_queue_size());
        let (response_send, response_recv) = mpsc::channel(*response_queue_size());
        let guard = ReqRepGuard::spawn(move |cancel| {
            Actor::new(
                cancel,
                incoming,
                outgoing,
                request_recv,
                accept_send,
                response_recv,
            )
            .run()
        });
        (
            Self {
                request_send,
                accept_recv,
                response_send,
            },
            guard,
        )
    }

    pub async fn request(&self, message: N) -> Result<M, Error> {
        let (result_send, result_recv) = oneshot::channel();
        self.request_send
            .send((message, result_send))
            .await
            .map_err(|_| new_shutdown_error())?;
        result_recv.await.map_err(|_| new_shutdown_error())?
    }

    pub async fn accept(&self) -> Option<(M, Sender<N, E>)>
    where
        M: Message<Endpoint = E>,
        E: Clone,
    {
        self.accept_recv.recv().await.map(|(message, result_recv)| {
            let sender = Sender::new(
                self.response_send.clone(),
                result_recv,
                message.endpoint().clone(),
            );
            (message, sender)
        })
    }
}

impl<N, E> Sender<N, E> {
    fn new(
        response_send: mpsc::Sender<Result<N, E>>,
        result_recv: ResultRecv<()>,
        endpoint: E,
    ) -> Self {
        Self {
            response_send,
            result_recv,
            endpoint: Some(endpoint),
        }
    }

    // The user may only call `send` once.
    pub async fn send(mut self, message: N) -> Result<(), Error>
    where
        N: Message<Endpoint = E>,
        E: fmt::Debug + PartialEq,
    {
        // It does not seem like a good idea to allow the user to send a response to a different
        // endpoint.
        assert_eq!(message.endpoint(), &self.endpoint.take().unwrap());
        self.response_send
            .send(Ok(message))
            .await
            .map_err(|_| new_shutdown_error())?;
        (&mut self.result_recv)
            .await
            .map_err(|_| new_shutdown_error())?
    }
}

impl<N, E> Drop for Sender<N, E> {
    fn drop(&mut self) {
        if let Some(endpoint) = self.endpoint.take() {
            // We make our best effort to send the "cancel reqrep response entry" message to the
            // actor, but what should we do if the queue is full?  Should we crash the process?
            if matches!(
                self.response_send.try_send(Err(endpoint)),
                Err(mpsc::error::TrySendError::Full(_)),
            ) {
                tracing::warn!("reqrep response queue is full");
            }
        }
    }
}

impl<M, N, E, I, O> Actor<M, N, E, I, O>
where
    M: Message<Endpoint = E>,
    N: Message<Endpoint = E>,
    E: Clone + fmt::Debug + Eq + Hash + PartialEq + Send,
    I: Stream<Item = Result<M, Error>> + Unpin,
    O: Sink<N, Error = Error> + Unpin,
{
    fn new(
        cancel: Cancel,
        incoming: I,
        outgoing: O,
        request_recv: mpsc::Receiver<(N, ResultSend<M>)>,
        accept_send: mpmc::Sender<(M, ResultRecv<()>)>,
        response_recv: mpsc::Receiver<Result<N, E>>,
    ) -> Self {
        Self {
            cancel,
            incoming,
            outgoing,
            request_recv,
            request_timeout: *request_timeout(),
            request_deadlines: VecDeque::new(),
            accept_send,
            response_recv,
            reqrep: HashMap::new(),
        }
    }

    async fn run(mut self) -> Result<(), Error> {
        let mut deadline = None;
        tokio::pin! { let timeout = OptionFuture::from(None); }
        loop {
            let next_deadline = self.next_deadline();
            if deadline != next_deadline {
                deadline = next_deadline;
                timeout.set(OptionFuture::from(deadline.map(time::sleep_until)));
            }

            tokio::select! {
                () = self.cancel.wait() => break,

                incoming = self.incoming.next() => {
                    match incoming {
                        Some(Ok(message)) => self.handle_incoming(message),
                        Some(Err(error)) => tracing::warn!(%error, "reqrep incoming error"),
                        None => break,
                    }
                }

                request = self.request_recv.recv() => {
                    let Some(request) = request else { break };
                    self.handle_request(request).await;
                }

                Some(()) = &mut timeout => {
                    self.handle_timeout(Instant::now());
                }

                response = self.response_recv.recv() => {
                    let Some(response) = response else { break };
                    self.handle_response(response).await;
                }
            }
        }
        self.outgoing.close().await
    }

    fn next_deadline(&self) -> Option<Instant> {
        self.request_deadlines
            .front()
            .map(|(deadline, _)| deadline)
            .copied()
    }

    //
    // In general, we are ignoring the error that may occur when `result_recv` is dropped, thus
    // calling `send_and_forget`.
    //

    #[tracing::instrument(name = "reqrep", fields(endpoint = ?message.endpoint()), skip_all)]
    fn handle_incoming(&mut self, message: M) {
        match self.reqrep.entry(message.endpoint().clone()) {
            Entry::Occupied(entry) => match entry.get() {
                State::Request(_) => {
                    let State::Request(result_send) = entry.remove() else {
                        std::unreachable!()
                    };
                    result_send.send_and_forget(Ok(message));
                }
                State::Response(_) => {
                    tracing::warn!("prior request-response; drop request");
                }
            },
            Entry::Vacant(entry) => {
                let (result_send, result_recv) = oneshot::channel();
                match self.accept_send.try_send((message, result_recv)) {
                    Ok(()) => {
                        entry.insert(State::Response(result_send));
                    }
                    Err(error) => match error {
                        mpmc::error::TrySendError::Full(_) => {
                            tracing::warn!("accept queue full; drop request");
                        }
                        mpmc::error::TrySendError::Closed(_) => {
                            tracing::warn!("accept queue closed; drop request");
                        }
                    },
                }
            }
        }
    }

    async fn handle_request(&mut self, (message, result_send): (N, ResultSend<M>)) {
        let endpoint = message.endpoint().clone();

        match self.reqrep.entry(endpoint.clone()) {
            Entry::Occupied(_) => {
                result_send.send_and_forget(Err(new_addr_in_use_error(&endpoint)));
                return;
            }
            Entry::Vacant(entry) => {
                entry.insert(State::Request(result_send));
                self.request_deadlines
                    .push_back((Instant::now() + self.request_timeout, endpoint.clone()));
            }
        }

        if let Err(error) = self.outgoing.send(message).await {
            let Some(State::Request(result_send)) = self.reqrep.remove(&endpoint) else {
                std::panic!("expect reqrep request entry: {endpoint:?}");
            };
            result_send.send_and_forget(Err(error));
        }
    }

    fn handle_timeout(&mut self, now: Instant) {
        while let Some((deadline, _)) = self.request_deadlines.front() {
            if &now < deadline {
                break;
            }
            let (_, endpoint) = self.request_deadlines.pop_front().unwrap();
            match self.reqrep.remove(&endpoint) {
                Some(State::Request(result_send)) => result_send.send_and_forget(Err(Error::new(
                    ErrorKind::TimedOut,
                    error::Error::RequestTimeout,
                ))),
                Some(_) => std::panic!("expect reqrep request entry: {endpoint:?}"),
                None => {}
            }
        }
    }

    async fn handle_response(&mut self, message: Result<N, E>) {
        match message {
            Ok(message) => {
                let result_send = self.remove_response(message.endpoint());
                result_send.send_and_forget(self.outgoing.send(message).await);
            }
            Err(endpoint) => {
                // The user has dropped `Sender` without providing a response.
                let _ = self.remove_response(&endpoint);
            }
        }
    }

    fn remove_response(&mut self, endpoint: &E) -> ResultSend<()> {
        let Some(State::Response(result_send)) = self.reqrep.remove(endpoint) else {
            std::panic!("expect reqrep response entry: {endpoint:?}");
        };
        result_send
    }
}

trait SendAndForget<T> {
    fn send_and_forget(self, t: T);
}

impl<T> SendAndForget<T> for oneshot::Sender<T> {
    fn send_and_forget(self, t: T) {
        let _ = self.send(t);
    }
}

fn new_shutdown_error() -> Error {
    Error::new(ErrorKind::ConnectionAborted, error::Error::Shutdown)
}

fn new_addr_in_use_error<Endpoint>(endpoint: &Endpoint) -> Error
where
    Endpoint: fmt::Debug,
{
    Error::new(
        ErrorKind::AddrInUse,
        error::Error::RequestConflict {
            endpoint: format!("{endpoint:?}"),
        },
    )
}

#[cfg(test)]
mod test_harness {
    use futures::channel::mpsc as futures_mpsc;

    use super::*;

    type Message = (String, String);
    type Endpoint = String;

    pub type Outgoing = impl Sink<Message, Error = Error> + Unpin;

    // TODO: Make use of all mocked fields.
    #[allow(dead_code)]
    pub struct MockActor {
        pub cancel: Cancel,
        pub incoming_send: futures_mpsc::UnboundedSender<Result<Message, Error>>,
        pub outgoing_recv: futures_mpsc::UnboundedReceiver<Message>,
        pub request_send: mpsc::Sender<(Message, ResultSend<Message>)>,
        pub accept_recv: mpmc::Receiver<(Message, ResultRecv<()>)>,
        pub response_send: mpsc::Sender<Result<Message, Endpoint>>,
    }

    impl ReqRep<Message, Message, Endpoint> {
        pub fn spawn_mock() -> (
            Self,
            ReqRepGuard,
            futures_mpsc::UnboundedSender<Result<Message, Error>>,
            futures_mpsc::UnboundedReceiver<Message>,
        ) {
            let (incoming_send, incoming_recv) = futures_mpsc::unbounded();
            let (outgoing_send, outgoing_recv) = futures_mpsc::unbounded();
            let (this, guard) =
                ReqRep::spawn(incoming_recv, outgoing_send.sink_map_err(Error::other));
            (this, guard, incoming_send, outgoing_recv)
        }
    }

    impl
        Actor<
            Message,
            Message,
            Endpoint,
            futures_mpsc::UnboundedReceiver<Result<Message, Error>>,
            Outgoing,
        >
    {
        #[define_opaque(Outgoing)]
        pub fn new_mock() -> (Self, MockActor) {
            let cancel = Cancel::new();
            let (incoming_send, incoming_recv) = futures_mpsc::unbounded();
            let (outgoing_send, outgoing_recv) = futures_mpsc::unbounded();
            let (request_send, request_recv) = mpsc::channel(*request_queue_size());
            let (accept_send, accept_recv) = mpmc::channel(*accept_queue_size());
            let (response_send, response_recv) = mpsc::channel(*response_queue_size());
            (
                Self::new(
                    cancel.clone(),
                    incoming_recv,
                    outgoing_send.sink_map_err(Error::other),
                    request_recv,
                    accept_send,
                    response_recv,
                ),
                MockActor {
                    cancel,
                    incoming_send,
                    outgoing_recv,
                    request_send,
                    accept_recv,
                    response_send,
                },
            )
        }
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use futures::{channel::mpsc as futures_mpsc, stream::StreamExt};
    use snafu::prelude::*;
    use tokio::time;

    use super::*;

    #[derive(Clone, Debug, Eq, PartialEq, Snafu)]
    struct OtherError;

    fn msg(endpoint: &str, payload: &str) -> (String, String) {
        (endpoint.into(), payload.into())
    }

    fn assert_err<T, E>(result: Result<T, Error>, kind: ErrorKind, inner: E)
    where
        T: fmt::Debug,
        E: PartialEq,
        E: std::error::Error + Send + Sync + 'static, // Required by `downcast`.
    {
        let error = result.unwrap_err();
        assert_eq!(error.kind(), kind);
        assert_matches!(error.downcast::<E>(), Ok(e) if e == inner);
    }

    fn assert_actor<M, N, I, O>(
        actor: &Actor<M, N, String, I, O>,
        expect_request_endpoints: &[&str],
        expect_response_endpoints: &[&str],
    ) {
        type Match<M> = fn(&State<M>) -> bool;
        let match_request: Match<M> = |state: &State<M>| matches!(state, State::Request(_));
        let match_response: Match<M> = |state: &State<M>| matches!(state, State::Response(_));

        for (match_state, expect) in [
            (match_request, expect_request_endpoints),
            (match_response, expect_response_endpoints),
        ] {
            let mut endpoints: Vec<_> = actor
                .reqrep
                .iter()
                .filter_map(|(endpoint, state)| {
                    if match_state(state) {
                        Some(endpoint)
                    } else {
                        None
                    }
                })
                .collect();
            endpoints.sort();
            assert_eq!(endpoints, expect);
        }
    }

    //
    // TODO: Can we write these tests without using `time::sleep`?
    //

    #[tokio::test]
    async fn request() {
        let (reqrep, mut guard, mut mock_incoming, mut mock_outgoing) = ReqRep::spawn_mock();

        let task = {
            let reqrep = reqrep.clone();
            tokio::spawn(async move { reqrep.request(msg("x", "ping")).await })
        };
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        assert_matches!(mock_incoming.send(Ok(msg("x", "pong"))).await, Ok(()));
        assert_matches!(task.await, Ok(Ok(m)) if m == msg("x", "pong"));

        assert_matches!(guard.shutdown().await, Ok(Ok(())));
        assert_eq!(mock_outgoing.next().await, Some(msg("x", "ping")));
        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test]
    async fn request_conflict() {
        let (reqrep, mut guard, mut mock_incoming, mut mock_outgoing) = ReqRep::spawn_mock();

        assert_matches!(mock_incoming.send(Ok(msg("x", "pong"))).await, Ok(()));
        time::sleep(Duration::from_millis(10)).await;
        assert_err(
            reqrep.request(msg("x", "ping")).await,
            ErrorKind::AddrInUse,
            error::Error::RequestConflict {
                endpoint: format!("{:?}", "x"),
            },
        );

        assert_matches!(guard.shutdown().await, Ok(Ok(())));
        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test]
    async fn request_outgoing_closed() {
        let (reqrep, mut guard, _mock_incoming, _) = ReqRep::spawn_mock();

        let error = reqrep.request(msg("x", "ping")).await.unwrap_err();
        assert_eq!(error.kind(), ErrorKind::Other);
        let inner = error.downcast::<futures_mpsc::SendError>().unwrap();
        assert_eq!(inner.is_disconnected(), true);

        assert_matches!(guard.shutdown().await, Ok(Ok(())));
    }

    #[tokio::test]
    async fn request_shutdown_before() {
        let (reqrep, mut guard, _mock_incoming, mut mock_outgoing) = ReqRep::spawn_mock();

        assert_matches!(guard.shutdown().await, Ok(Ok(())));
        assert_err(
            reqrep.request(msg("x", "foo")).await,
            ErrorKind::ConnectionAborted,
            error::Error::Shutdown,
        );

        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test]
    async fn request_shutdown_during() {
        let (reqrep, mut guard, _mock_incoming, mut mock_outgoing) = ReqRep::spawn_mock();

        let task = {
            let reqrep = reqrep.clone();
            tokio::spawn(async move { reqrep.request(msg("x", "ping")).await })
        };
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        assert_matches!(guard.shutdown().await, Ok(Ok(())));
        assert_err(
            task.await.unwrap(),
            ErrorKind::ConnectionAborted,
            error::Error::Shutdown,
        );

        assert_eq!(mock_outgoing.next().await, Some(msg("x", "ping")));
        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test]
    async fn response() {
        let (reqrep, mut guard, mut mock_incoming, mut mock_outgoing) = ReqRep::spawn_mock();

        let task = {
            let reqrep = reqrep.clone();
            tokio::spawn(async move { reqrep.accept().await })
        };
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        assert_matches!(mock_incoming.send(Ok(msg("x", "ping"))).await, Ok(()));
        let (message, sender) = task.await.unwrap().unwrap();
        assert_eq!(message, msg("x", "ping"));
        assert_matches!(sender.send(msg("x", "pong")).await, Ok(()));

        assert_matches!(guard.shutdown().await, Ok(Ok(())));
        assert_eq!(mock_outgoing.next().await, Some(msg("x", "pong")));
        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test]
    async fn response_outgoing_closed() {
        let (reqrep, mut guard, mut mock_incoming, _) = ReqRep::spawn_mock();

        let task = {
            let reqrep = reqrep.clone();
            tokio::spawn(async move { reqrep.accept().await })
        };
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        assert_matches!(mock_incoming.send(Ok(msg("x", "ping"))).await, Ok(()));
        let (message, sender) = task.await.unwrap().unwrap();
        assert_eq!(message, msg("x", "ping"));
        let error = sender.send(msg("x", "pong")).await.unwrap_err();
        assert_eq!(error.kind(), ErrorKind::Other);
        let inner = error.downcast::<futures_mpsc::SendError>().unwrap();
        assert_eq!(inner.is_disconnected(), true);

        assert_matches!(guard.shutdown().await, Ok(Ok(())));
    }

    #[tokio::test]
    async fn accept_incoming_closed() {
        let (reqrep, mut guard, _, _) = ReqRep::spawn_mock();
        assert_matches!(reqrep.accept().await, None);
        assert_matches!(guard.shutdown().await, Ok(Ok(())));
    }

    #[tokio::test]
    async fn accept_shutdown_before() {
        let (reqrep, mut guard, _mock_incoming, mut mock_outgoing) = ReqRep::spawn_mock();

        assert_matches!(guard.shutdown().await, Ok(Ok(())));
        assert_matches!(reqrep.accept().await, None);

        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test]
    async fn accept_shutdown_during() {
        let (reqrep, mut guard, _mock_incoming, mut mock_outgoing) = ReqRep::spawn_mock();

        let task = {
            let reqrep = reqrep.clone();
            tokio::spawn(async move { reqrep.accept().await })
        };
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        assert_matches!(guard.shutdown().await, Ok(Ok(())));
        assert_matches!(task.await, Ok(None));

        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test]
    async fn accept_without_response() {
        let (reqrep, mut guard, mut mock_incoming, mut mock_outgoing) = ReqRep::spawn_mock();

        let task = {
            let reqrep = reqrep.clone();
            tokio::spawn(async move { reqrep.accept().await })
        };
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        assert_matches!(mock_incoming.send(Ok(msg("x", "ping"))).await, Ok(()));
        assert_matches!(task.await, Ok(Some((m, _))) if m == msg("x", "ping"));

        // We may send a new request because the `reqrep` entry is dropped.
        let task = {
            let reqrep = reqrep.clone();
            tokio::spawn(async move { reqrep.request(msg("x", "foo")).await })
        };
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        assert_matches!(mock_incoming.send(Ok(msg("x", "bar"))).await, Ok(()));
        assert_matches!(task.await, Ok(Ok(m)) if m == msg("x", "bar"));

        assert_matches!(guard.shutdown().await, Ok(Ok(())));
        assert_eq!(mock_outgoing.next().await, Some(msg("x", "foo")));
        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test]
    async fn incoming_error_ignored() {
        let (reqrep, mut guard, mut mock_incoming, mut mock_outgoing) = ReqRep::spawn_mock();

        let task = {
            let reqrep = reqrep.clone();
            tokio::spawn(async move { reqrep.accept().await })
        };

        assert_matches!(
            mock_incoming.send(Err(Error::other(OtherError))).await,
            Ok(()),
        );
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        assert_matches!(guard.shutdown().await, Ok(Ok(())));
        assert_eq!(mock_outgoing.next().await, None);
        assert_matches!(task.await, Ok(None));
    }

    #[tokio::test]
    async fn handle_incoming_request() {
        let (mut actor, mut mock_actor) = Actor::new_mock();
        assert_actor(&actor, &[], &[]);

        let (result_send, result_recv) = oneshot::channel();
        actor.handle_request((msg("x", "ping"), result_send)).await;
        assert_actor(&actor, &["x"], &[]);

        actor.handle_incoming(msg("x", "pong"));
        assert_actor(&actor, &[], &[]);
        assert_matches!(result_recv.await, Ok(Ok(m)) if m == msg("x", "pong"));

        drop(actor);
        assert_matches!(mock_actor.outgoing_recv.next().await, Some(m) if m == msg("x", "ping"));
        assert_matches!(mock_actor.outgoing_recv.next().await, None);
        assert_matches!(mock_actor.accept_recv.recv().await, None);
    }

    #[tokio::test]
    async fn handle_incoming_response() {
        let (mut actor, mut mock_actor) = Actor::new_mock();
        assert_actor(&actor, &[], &[]);

        actor.handle_incoming(msg("x", "ping"));
        assert_actor(&actor, &[], &["x"]);
        actor.handle_incoming(msg("x", "spam"));
        assert_actor(&actor, &[], &["x"]);

        actor.handle_incoming(msg("y", "foo"));
        assert_actor(&actor, &[], &["x", "y"]);

        mock_actor.accept_recv.close();
        actor.handle_incoming(msg("z", "spam"));
        assert_actor(&actor, &[], &["x", "y"]);

        drop(actor);
        assert_matches!(mock_actor.outgoing_recv.next().await, None);
        assert_matches!(mock_actor.accept_recv.recv().await, Some((m, _)) if m == msg("x", "ping"));
        assert_matches!(mock_actor.accept_recv.recv().await, Some((m, _)) if m == msg("y", "foo"));
        assert_matches!(mock_actor.accept_recv.recv().await, None);
    }

    #[tokio::test]
    async fn handle_request_outgoing_closed() {
        let (mut actor, mut mock_actor) = Actor::new_mock();
        assert_actor(&actor, &[], &[]);

        mock_actor.outgoing_recv.close();
        let (result_send, result_recv) = oneshot::channel();
        actor.handle_request((msg("x", "ping"), result_send)).await;
        assert_actor(&actor, &[], &[]);
        let error = result_recv.await.unwrap().unwrap_err();
        assert_eq!(error.kind(), ErrorKind::Other);
        let inner = error.downcast::<futures_mpsc::SendError>().unwrap();
        assert_eq!(inner.is_disconnected(), true);

        drop(actor);
        assert_matches!(mock_actor.outgoing_recv.next().await, None);
    }

    #[tokio::test]
    async fn handle_request_addr_in_use_error() {
        let (mut actor, mut mock_actor) = Actor::new_mock();
        assert_actor(&actor, &[], &[]);

        let (result_send, _) = oneshot::channel();
        actor.handle_request((msg("x", "foo"), result_send)).await;
        assert_actor(&actor, &["x"], &[]);

        let (result_send, result_recv) = oneshot::channel();
        actor.handle_request((msg("x", "bar"), result_send)).await;
        assert_actor(&actor, &["x"], &[]);
        assert_err(
            result_recv.await.unwrap(),
            ErrorKind::AddrInUse,
            error::Error::RequestConflict {
                endpoint: format!("{:?}", "x"),
            },
        );

        drop(actor);
        assert_matches!(mock_actor.outgoing_recv.next().await, Some(m) if m == msg("x", "foo"));
        assert_matches!(mock_actor.outgoing_recv.next().await, None);
    }

    #[tokio::test]
    async fn handle_response() {
        let (mut actor, mut mock_actor) = Actor::new_mock();
        assert_actor(&actor, &[], &[]);

        actor.handle_incoming(msg("x", "ping"));
        assert_actor(&actor, &[], &["x"]);

        let (message, result_recv) = mock_actor.accept_recv.recv().await.unwrap();
        assert_eq!(message, msg("x", "ping"));

        actor.handle_response(Ok(msg("x", "pong"))).await;
        assert_actor(&actor, &[], &[]);
        assert_matches!(result_recv.await, Ok(Ok(())));

        drop(actor);
        assert_matches!(mock_actor.outgoing_recv.next().await, Some(m) if m == msg("x", "pong"));
        assert_matches!(mock_actor.outgoing_recv.next().await, None);
    }

    #[tokio::test]
    async fn handle_response_sender_dropped() {
        let (mut actor, mut mock_actor) = Actor::new_mock();
        assert_actor(&actor, &[], &[]);

        actor.handle_incoming(msg("x", "ping"));
        assert_actor(&actor, &[], &["x"]);

        let (message, result_recv) = mock_actor.accept_recv.recv().await.unwrap();
        assert_eq!(message, msg("x", "ping"));

        actor.handle_response(Err("x".into())).await;
        assert_actor(&actor, &[], &[]);
        assert_matches!(result_recv.await, Err(_));

        drop(actor);
        assert_matches!(mock_actor.outgoing_recv.next().await, None);
    }
}
