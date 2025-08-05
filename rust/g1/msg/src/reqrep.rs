use std::fmt;
use std::hash::Hash;
use std::marker::PhantomData;
use std::sync::Arc;
use std::time::Duration;

use futures::sink::{self, SinkExt};
use futures::stream::{self, TryStreamExt};
use tokio::sync::{Mutex, mpsc, oneshot};
use tokio::time::{self, Instant};

use g1_base::collections::HashOrderedMap;
use g1_tokio::task::JoinGuard;

// TODO: How do we remove `Send + 'static` from `Protocol`, given that `P` is merely a phantom type
// parameter?
pub trait Protocol: Send + 'static {
    // We use `Id` to associate `Incoming` and `Outgoing` messages.
    // TODO: How do we remove `Send + Sync` from `Id`?
    type Id: Clone + fmt::Debug + Eq + Hash + Send + Sync;
    type Incoming: fmt::Debug + Send;
    type Outgoing: Send;

    // It represents severe error conditions that force the actor to exit.  Do not confuse this
    // with an ordinary error response, which is encoded in the incoming messages.
    type Error: Send + 'static;

    fn incoming_id(incoming: &Self::Incoming) -> Self::Id;
    fn outgoing_id(outgoing: &Self::Outgoing) -> Self::Id;
}

pub trait Stream<P: Protocol> =
    stream::Stream<Item = Result<P::Incoming, P::Error>> + Send + Unpin + 'static;

pub trait Sink<P: Protocol> = sink::Sink<P::Outgoing, Error = P::Error> + Send + Unpin + 'static;

#[derive(Clone, Debug)]
pub struct Spawner<P> {
    _protocol: PhantomData<P>,
    accept_queue_size: usize,
    request_timeout: Duration,
}

pub type Guard<P: Protocol> = JoinGuard<Result<(), P::Error>>;

pub type ResponseRecv<P: Protocol> = oneshot::Receiver<P::Incoming>;
pub struct ResponseSend<P: Protocol>(ReqRep<P>);

struct ReqRepActor<P, I, O>
where
    P: Protocol,
{
    _protocol: PhantomData<P>,

    incoming: I,
    outgoing: O,

    accept_send: AcceptSend<P>,

    // We maintain entries in ascending order by `deadline`.  This is possible because
    // `Instant::now()` is monotonic and `request_timeout` is constant.
    requests: Requests<P>,
    request_timeout: Duration,
}

// TODO: Should we use an `mpmc` channel instead?
type AcceptRecv<P: Protocol> = Arc<Mutex<mpsc::Receiver<P::Incoming>>>;
type AcceptSend<P: Protocol> = mpsc::Sender<P::Incoming>;

type Requests<P: Protocol> = HashOrderedMap<P::Id, (Instant, oneshot::Sender<P::Incoming>)>;

#[g1_actor::actor(
    stub(
        derive(),
        pub, ReqRep, struct {
            accept_recv: AcceptRecv<P>,
        },
        spawn(spawn_impl),
    ),
    loop_(
        type Result<(), P::Error>,
        return Ok(()),
    ),
)]
impl<P, I, O> ReqRepActor<P, I, O>
where
    P: Protocol,
    I: Stream<P>,
    O: Sink<P>,
{
    fn new(
        incoming: I,
        outgoing: O,
        accept_send: AcceptSend<P>,
        request_timeout: Duration,
    ) -> Self {
        Self {
            _protocol: PhantomData,

            incoming,
            outgoing,

            accept_send,

            requests: Requests::<P>::new(),
            request_timeout,
        }
    }

    #[actor::loop_(react = {
        let result = self.incoming.try_next();
        match result? {
            Some(incoming) => self.on_incoming(incoming),
            None => break,
        }
    })]
    fn on_incoming(&mut self, incoming: P::Incoming) {
        match self.requests.remove(&P::incoming_id(&incoming)) {
            Some((deadline, response_send)) => {
                if deadline.elapsed() == Duration::ZERO {
                    let _ = response_send.send(incoming);
                } else {
                    tracing::warn!(?incoming, "recv response after timeout");
                }
            }
            None => {
                if let Err(error) = self.accept_send.try_send(incoming) {
                    let incoming = error.into_inner();
                    tracing::warn!(?incoming, "accept full; drop");
                }
            }
        }
    }

    #[actor::loop_(react = {
        let Some(()) = Self::timeout(&self.requests);
        self.on_timeout();
    })]
    async fn timeout(requests: &Requests<P>) -> Option<()> {
        time::sleep_until(requests.values().next()?.0).await;
        Some(())
    }

    fn on_timeout(&mut self) {
        let timeout_ids = self
            .requests
            .iter()
            .take_while(|(_, entry)| entry.0.elapsed() != Duration::ZERO)
            .map(|(id, _)| id.clone())
            .collect::<Vec<_>>();
        for id in timeout_ids {
            tracing::warn!(?id, "request timeout");
            assert!(self.requests.remove(&id).is_some());
        }
    }

    #[actor::method(return { let result: ResponseRecv<P> = result?; })]
    async fn send_request(&mut self, outgoing: P::Outgoing) -> Result<ResponseRecv<P>, P::Error> {
        let id = P::outgoing_id(&outgoing);
        self.outgoing.send(outgoing).await?;
        Ok(self.create_request(id))
    }

    fn create_request(&mut self, id: P::Id) -> ResponseRecv<P> {
        let (response_send, response_recv) = oneshot::channel();
        let entry = (Instant::now() + self.request_timeout, response_send);
        assert!(self.requests.insert(id, entry).is_none());
        response_recv
    }

    #[actor::method(return { let result: () = result?; })]
    async fn send_response(&mut self, outgoing: P::Outgoing) -> Result<(), P::Error> {
        self.outgoing.send(outgoing).await
    }
}

impl<P> Default for Spawner<P> {
    fn default() -> Self {
        Self::new()
    }
}

impl<P> Spawner<P> {
    pub fn new() -> Self {
        Self {
            _protocol: PhantomData,
            accept_queue_size: 16,
            request_timeout: Duration::from_secs(2),
        }
    }

    pub fn accept_queue_size(mut self, accept_queue_size: usize) -> Self {
        self.accept_queue_size = accept_queue_size;
        self
    }

    pub fn request_timeout(mut self, request_timeout: Duration) -> Self {
        self.request_timeout = request_timeout;
        self
    }

    pub fn spawn<I, O>(self, incoming: I, outgoing: O) -> (ReqRep<P>, Guard<P>)
    where
        P: Protocol,
        I: Stream<P>,
        O: Sink<P>,
    {
        let Self {
            _protocol,
            accept_queue_size,
            request_timeout,
        } = self;
        let (accept_send, accept_recv) = mpsc::channel(accept_queue_size);
        ReqRep::spawn_impl(
            Arc::new(Mutex::new(accept_recv)),
            ReqRepActor::new(incoming, outgoing, accept_send, request_timeout),
        )
    }
}

impl<P> ReqRep<P>
where
    P: Protocol,
{
    pub fn spawner() -> Spawner<P> {
        Spawner::new()
    }

    pub fn spawn<I, O>(incoming: I, outgoing: O) -> (Self, Guard<P>)
    where
        I: Stream<P>,
        O: Sink<P>,
    {
        Self::spawner().spawn(incoming, outgoing)
    }

    pub async fn accept(&self) -> Option<(P::Incoming, ResponseSend<P>)> {
        let request = self.accept_recv.lock().await.recv().await?;
        Some((request, ResponseSend(self.clone())))
    }

    // TODO: Should we return `Result<ResponseRecv<P>, Option<(P::Outgoing,)>>` instead?
    pub async fn request(&self, request: P::Outgoing) -> Option<ResponseRecv<P>> {
        self.send_request(request).await.ok()
    }
}

impl<P> ResponseSend<P>
where
    P: Protocol,
{
    // TODO: Should we return `Result<(), Option<(P::Outgoing,)>>` instead?
    pub async fn send(self, response: P::Outgoing) {
        let _ = self.0.send_response(response).await;
    }
}

//
// Implement `Clone` and `Debug` manually to avoid requiring `P: Clone` and `P: Debug`.
//

impl<P> Clone for ReqRep<P>
where
    P: Protocol,
{
    fn clone(&self) -> Self {
        Self {
            __message_queue: self.__message_queue.clone(),
            accept_recv: self.accept_recv.clone(),
        }
    }
}

impl<P> Clone for ResponseSend<P>
where
    P: Protocol,
{
    fn clone(&self) -> Self {
        Self(self.0.clone())
    }
}

impl<P> fmt::Debug for ReqRep<P>
where
    P: Protocol,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ReqRep")
            .field("__message_queue", &self.__message_queue)
            .field("accept_recv", &self.accept_recv)
            .finish()
    }
}

impl<P> fmt::Debug for ResponseSend<P>
where
    P: Protocol,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_tuple("ResponseSend").field(&self.0).finish()
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use futures::channel::mpsc::{
        self as futures_mpsc, SendError, UnboundedReceiver, UnboundedSender,
    };
    use futures::stream::StreamExt;

    use super::*;

    struct TestP;

    type TestM = (&'static str, &'static str);

    impl Protocol for TestP {
        type Id = &'static str;
        type Incoming = TestM;
        type Outgoing = TestM;

        type Error = SendError;

        fn incoming_id((id, _): &Self::Incoming) -> Self::Id {
            id
        }

        fn outgoing_id((id, _): &Self::Outgoing) -> Self::Id {
            id
        }
    }

    type TestActor =
        ReqRepActor<TestP, UnboundedReceiver<Result<TestM, SendError>>, UnboundedSender<TestM>>;

    fn mock_actor() -> (TestActor, UnboundedReceiver<TestM>, mpsc::Receiver<TestM>) {
        let (_, incoming_recv) = futures_mpsc::unbounded();
        let (outgoing_send, outgoing_recv) = futures_mpsc::unbounded();
        let (accept_send, accept_recv) = mpsc::channel(16);
        (
            ReqRepActor::new(
                incoming_recv,
                outgoing_send,
                accept_send,
                Duration::from_secs(2),
            ),
            outgoing_recv,
            accept_recv,
        )
    }

    fn mock_reqrep() -> (
        ReqRep<TestP>,
        Guard<TestP>,
        UnboundedSender<Result<TestM, SendError>>,
        UnboundedReceiver<TestM>,
    ) {
        let (incoming_send, incoming_recv) = futures_mpsc::unbounded();
        let (outgoing_send, outgoing_recv) = futures_mpsc::unbounded();
        let (reqrep, guard) = ReqRep::spawn(incoming_recv, outgoing_send);
        (reqrep, guard, incoming_send, outgoing_recv)
    }

    impl<P, I, O> ReqRepActor<P, I, O>
    where
        P: Protocol,
    {
        fn assert_requests(&self, expect: &[(P::Id, Instant)]) {
            assert_eq!(
                self.requests
                    .iter()
                    .map(|(id, (deadline, _))| (id.clone(), *deadline))
                    .collect::<Vec<_>>(),
                expect,
            );
        }
    }

    #[tokio::test(start_paused = true)]
    async fn on_incoming() {
        let (mut actor, mut mock_outgoing, mut mock_accept) = mock_actor();

        let t0 = Instant::now();
        let d1 = t0 + Duration::from_secs(2);
        let r1 = actor.send_request(("id-1", "a")).await.unwrap();
        actor.assert_requests(&[("id-1", d1)]);

        actor.on_incoming(("id-2", "b"));
        actor.assert_requests(&[("id-1", d1)]);
        assert_eq!(mock_accept.recv().await, Some(("id-2", "b")));

        actor.on_incoming(("id-1", "c"));
        actor.assert_requests(&[]);
        assert_matches!(r1.await, Ok(("id-1", "c")));

        drop(actor);
        assert_eq!(mock_outgoing.next().await, Some(("id-1", "a")));
        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test(start_paused = true)]
    async fn on_incoming_timeout() {
        let (mut actor, mut mock_outgoing, _) = mock_actor();

        let t0 = Instant::now();
        let d = t0 + Duration::from_secs(2);
        let r2 = actor.send_request(("id-2", "a")).await.unwrap();
        let r1 = actor.send_request(("id-1", "b")).await.unwrap();
        actor.assert_requests(&[("id-2", d), ("id-1", d)]);

        time::advance(Duration::from_millis(2000)).await;
        actor.on_incoming(("id-1", "c"));
        actor.assert_requests(&[("id-2", d)]);
        assert_matches!(r1.await, Ok(("id-1", "c")));

        time::advance(Duration::from_millis(100)).await;
        actor.on_incoming(("id-2", "d"));
        actor.assert_requests(&[]);
        assert_matches!(r2.await, Err(oneshot::error::RecvError { .. }));

        drop(actor);
        assert_eq!(mock_outgoing.next().await, Some(("id-2", "a")));
        assert_eq!(mock_outgoing.next().await, Some(("id-1", "b")));
        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test(start_paused = true)]
    async fn timeout() {
        let (mut actor, mut mock_outgoing, _) = mock_actor();

        let t0 = Instant::now();
        let d1 = t0 + Duration::from_secs(2);

        actor.assert_requests(&[]);
        assert_eq!(TestActor::timeout(&actor.requests).await, None);

        assert_matches!(actor.send_request(("id-1", "a")).await, Ok(_));
        actor.assert_requests(&[("id-1", d1)]);
        assert_eq!(TestActor::timeout(&actor.requests).await, Some(()));

        drop(actor);
        assert_eq!(mock_outgoing.next().await, Some(("id-1", "a")));
        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test(start_paused = true)]
    async fn on_timeout() {
        let (mut actor, mut mock_outgoing, _) = mock_actor();
        actor.assert_requests(&[]);

        let t0 = Instant::now();
        let d1 = t0 + Duration::from_secs(2);
        let d2 = t0 + Duration::from_millis(100) + Duration::from_secs(2);
        let d3 = t0 + Duration::from_millis(200) + Duration::from_secs(2);

        let r1 = actor.send_request(("id-1", "a")).await.unwrap();
        time::advance(Duration::from_millis(100)).await;
        let r2 = actor.send_request(("id-2", "b")).await.unwrap();
        time::advance(Duration::from_millis(100)).await;
        assert_matches!(actor.send_request(("id-3", "c")).await, Ok(_));
        actor.assert_requests(&[("id-1", d1), ("id-2", d2), ("id-3", d3)]);

        for _ in 0..3 {
            actor.on_timeout();
            actor.assert_requests(&[("id-1", d1), ("id-2", d2), ("id-3", d3)]);
        }

        time::advance(Duration::from_millis(1700)).await;
        assert_eq!(Instant::now(), d1 - Duration::from_millis(100));
        for _ in 0..3 {
            actor.on_timeout();
            actor.assert_requests(&[("id-1", d1), ("id-2", d2), ("id-3", d3)]);
        }

        time::advance(Duration::from_millis(100)).await;
        assert_eq!(Instant::now(), d1);
        for _ in 0..3 {
            actor.on_timeout();
            actor.assert_requests(&[("id-1", d1), ("id-2", d2), ("id-3", d3)]);
        }

        time::advance(Duration::from_millis(50)).await;
        for _ in 0..3 {
            actor.on_timeout();
            actor.assert_requests(&[("id-2", d2), ("id-3", d3)]);
        }
        assert_matches!(r1.await, Err(oneshot::error::RecvError { .. }));

        assert_eq!(Instant::now(), d2 - Duration::from_millis(50));
        for _ in 0..3 {
            actor.on_timeout();
            actor.assert_requests(&[("id-2", d2), ("id-3", d3)]);
        }

        time::advance(Duration::from_millis(50)).await;
        assert_eq!(Instant::now(), d2);
        for _ in 0..3 {
            actor.on_timeout();
            actor.assert_requests(&[("id-2", d2), ("id-3", d3)]);
        }

        time::advance(Duration::from_millis(50)).await;
        for _ in 0..3 {
            actor.on_timeout();
            actor.assert_requests(&[("id-3", d3)]);
        }
        assert_matches!(r2.await, Err(oneshot::error::RecvError { .. }));

        drop(actor);
        assert_eq!(mock_outgoing.next().await, Some(("id-1", "a")));
        assert_eq!(mock_outgoing.next().await, Some(("id-2", "b")));
        assert_eq!(mock_outgoing.next().await, Some(("id-3", "c")));
        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test(start_paused = true)]
    async fn send_request() {
        let (mut actor, mut mock_outgoing, _) = mock_actor();
        actor.assert_requests(&[]);

        let t0 = Instant::now();
        let d2 = t0 + Duration::from_secs(2);
        let d1 = t0 + Duration::from_secs(10 + 2);
        let d3 = t0 + Duration::from_secs(20 + 2);

        assert_matches!(actor.send_request(("id-2", "a")).await, Ok(_));
        actor.assert_requests(&[("id-2", d2)]);

        time::advance(Duration::from_secs(10)).await;
        assert_matches!(actor.send_request(("id-1", "b")).await, Ok(_));
        actor.assert_requests(&[("id-2", d2), ("id-1", d1)]);

        time::advance(Duration::from_secs(10)).await;
        assert_matches!(actor.send_request(("id-3", "c")).await, Ok(_));
        actor.assert_requests(&[("id-2", d2), ("id-1", d1), ("id-3", d3)]);

        drop(actor);
        assert_eq!(mock_outgoing.next().await, Some(("id-2", "a")));
        assert_eq!(mock_outgoing.next().await, Some(("id-1", "b")));
        assert_eq!(mock_outgoing.next().await, Some(("id-3", "c")));
        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test]
    async fn send_request_error() {
        let (mut actor, _, _) = mock_actor();
        assert_matches!(
            actor.send_request(("id-1", "a")).await,
            Err(SendError { .. }),
        );
    }

    #[tokio::test]
    async fn send_response() {
        let (mut actor, mut mock_outgoing, _) = mock_actor();
        actor.assert_requests(&[]);

        assert_matches!(actor.send_response(("id-1", "a")).await, Ok(()));
        actor.assert_requests(&[]);

        drop(actor);
        assert_eq!(mock_outgoing.next().await, Some(("id-1", "a")));
        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test]
    async fn send_response_error() {
        let (mut actor, _, _) = mock_actor();
        assert_matches!(
            actor.send_response(("id-1", "a")).await,
            Err(SendError { .. }),
        );
    }

    //
    // TODO: Can we write these tests without using `time::sleep`?
    //

    #[tokio::test]
    async fn accept() {
        let (reqrep, mut guard, mut mock_incoming, mut mock_outgoing) = mock_reqrep();

        let task = {
            let reqrep = reqrep.clone();
            tokio::spawn(async move { reqrep.accept().await })
        };
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        assert_eq!(mock_incoming.send(Ok(("foo", "bar"))).await, Ok(()));
        let (request, response_send) = task.await.unwrap().unwrap();
        assert_eq!(request, ("foo", "bar"));

        response_send.send(("spam", "egg")).await;
        assert_eq!(mock_outgoing.next().await, Some(("spam", "egg")));

        assert_matches!(guard.shutdown().await, Ok(Ok(())));
    }

    #[tokio::test]
    async fn request() {
        let (reqrep, mut guard, mut mock_incoming, mut mock_outgoing) = mock_reqrep();

        let task = {
            let reqrep = reqrep.clone();
            tokio::spawn(async move { reqrep.request(("id", "foo")).await.unwrap().await })
        };
        assert_eq!(mock_outgoing.next().await, Some(("id", "foo")));

        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        assert_eq!(mock_incoming.send(Ok(("id", "bar"))).await, Ok(()));
        assert_matches!(task.await, Ok(Ok(("id", "bar"))));

        assert_matches!(guard.shutdown().await, Ok(Ok(())));
    }

    #[tokio::test]
    async fn request_multiple() {
        let (reqrep, mut guard, mut mock_incoming, mut mock_outgoing) = mock_reqrep();

        let task_1 = {
            let reqrep = reqrep.clone();
            tokio::spawn(async move { reqrep.request(("id-1", "foo")).await.unwrap().await })
        };
        assert_eq!(mock_outgoing.next().await, Some(("id-1", "foo")));

        let task_2 = {
            let reqrep = reqrep.clone();
            tokio::spawn(async move { reqrep.request(("id-2", "bar")).await.unwrap().await })
        };
        assert_eq!(mock_outgoing.next().await, Some(("id-2", "bar")));

        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task_1.is_finished(), false);
        assert_eq!(task_2.is_finished(), false);

        assert_eq!(mock_incoming.send(Ok(("id-1", "spam"))).await, Ok(()));
        assert_eq!(mock_incoming.send(Ok(("id-2", "egg"))).await, Ok(()));
        assert_matches!(task_1.await, Ok(Ok(("id-1", "spam"))));
        assert_matches!(task_2.await, Ok(Ok(("id-2", "egg"))));

        assert_matches!(guard.shutdown().await, Ok(Ok(())));
    }

    #[tokio::test]
    async fn incoming_close() {
        let (reqrep, mut guard, mock_incoming, mut mock_outgoing) = mock_reqrep();

        let response_recv = reqrep.request(("foo", "bar")).await.unwrap();

        mock_incoming.close_channel();
        guard.join().await;
        assert_matches!(guard.take_result(), Ok(Ok(())));

        assert!(reqrep.accept().await.is_none());
        assert!(reqrep.request(("spam", "egg")).await.is_none());
        assert_matches!(response_recv.await, Err(oneshot::error::RecvError { .. }));

        assert_eq!(mock_outgoing.next().await, Some(("foo", "bar")));
        assert_eq!(mock_outgoing.next().await, None);
    }

    #[tokio::test]
    async fn outgoing_close() {
        let (reqrep, mut guard, mut mock_incoming, mut mock_outgoing) = mock_reqrep();

        mock_outgoing.close();

        // Although not very useful, we may still receive messages from `reqrep`.
        assert_eq!(mock_incoming.send(Ok(("foo", "bar"))).await, Ok(()));
        let (request, response_send) = reqrep.accept().await.unwrap();
        assert_eq!(request, ("foo", "bar"));

        response_send.send(("foo", "bar")).await;
        guard.join().await;
        assert_matches!(guard.take_result(), Ok(Err(SendError { .. })));
    }
}
