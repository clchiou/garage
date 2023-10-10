use std::pin::Pin;
use std::sync::{Arc, Mutex};
use std::task::{Context, Poll, Waker};

use futures::sink;

use g1_base::{sync::MutexExt, task};

pub fn fanin<const N: usize, Sink>(sink: Sink) -> [Fanin<Sink>; N] {
    let inner = Arc::new(Mutex::new(Inner::new(sink, N)));
    // We use `Vec`-copying because Rust currently cannot transmute from
    // `[MaybeUninit<Fanin<Sink>>; N]` to `[Fanin<Sink>; N]`.
    let mut fanins = Vec::with_capacity(N);
    for index in 0..N {
        fanins.push(Fanin::new(inner.clone(), index));
    }
    // We do not call `unwrap` because it requires `Debug`.
    match fanins.try_into() {
        Ok(fanins) => fanins,
        Err(_) => std::unreachable!(),
    }
}

#[derive(Debug)]
pub struct Fanin<Sink> {
    inner: Arc<Mutex<Inner<Sink>>>,
    index: usize,
}

#[derive(Debug)]
struct Inner<Sink> {
    sink: Sink,
    ready_wakers: Vec<Option<Waker>>,
    flush_wakers: Vec<Option<Waker>>,
    close_wakers: Vec<Option<Waker>>,
}

impl<Sink> Fanin<Sink> {
    fn new(inner: Arc<Mutex<Inner<Sink>>>, index: usize) -> Self {
        Self { inner, index }
    }
}

impl<Sink, Item, Error> sink::Sink<Item> for Fanin<Sink>
where
    Sink: sink::Sink<Item, Error = Error> + Unpin,
{
    type Error = Error;

    fn poll_ready(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Result<(), Self::Error>> {
        let this = self.get_mut();
        let mut inner = this.inner.must_lock();
        let poll = Pin::new(&mut inner.sink).poll_ready(context);
        if poll.is_pending() {
            task::update_waker(&mut inner.ready_wakers[this.index], context);
        }
        poll
    }

    fn start_send(self: Pin<&mut Self>, item: Item) -> Result<(), Self::Error> {
        let this = self.get_mut();
        let mut inner = this.inner.must_lock();
        wake_all(&mut inner.ready_wakers);
        Pin::new(&mut inner.sink).start_send(item)
    }

    fn poll_flush(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Result<(), Self::Error>> {
        let this = self.get_mut();
        let mut inner = this.inner.must_lock();
        let poll = Pin::new(&mut inner.sink).poll_flush(context);
        match poll {
            Poll::Ready(_) => wake_all(&mut inner.flush_wakers),
            Poll::Pending => task::update_waker(&mut inner.flush_wakers[this.index], context),
        }
        poll
    }

    fn poll_close(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Result<(), Self::Error>> {
        let this = self.get_mut();
        let mut inner = this.inner.must_lock();
        let poll = Pin::new(&mut inner.sink).poll_close(context);
        match poll {
            Poll::Ready(_) => wake_all(&mut inner.close_wakers),
            Poll::Pending => task::update_waker(&mut inner.close_wakers[this.index], context),
        }
        poll
    }
}

impl<Sink> Inner<Sink> {
    fn new(sink: Sink, num_fanins: usize) -> Self {
        Self {
            sink,
            ready_wakers: vec![None; num_fanins],
            flush_wakers: vec![None; num_fanins],
            close_wakers: vec![None; num_fanins],
        }
    }
}

fn wake_all(wakers: &mut Vec<Option<Waker>>) {
    for waker in wakers {
        if let Some(waker) = waker.take() {
            waker.wake();
        }
    }
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use futures::{
        channel::mpsc::{self, Receiver},
        sink::SinkExt,
        stream::StreamExt,
    };
    use tokio::time;

    use super::*;

    async fn assert_recv(mut recv: Receiver<usize>, expect: &[usize]) {
        recv.close();
        let mut items = Vec::with_capacity(expect.len());
        while let Some(item) = recv.next().await {
            items.push(item);
        }
        assert_eq!(items, expect);
    }

    #[tokio::test]
    async fn test_fanin() {
        let (send, recv) = mpsc::channel(10);
        let [mut f0, mut f1] = fanin(send);

        assert_eq!(f0.feed(0).await, Ok(()));
        assert_eq!(f1.feed(1).await, Ok(()));
        assert_eq!(f0.feed(2).await, Ok(()));
        assert_eq!(f1.feed(3).await, Ok(()));

        assert_eq!(f0.flush().await, Ok(()));
        assert_eq!(f1.flush().await, Ok(()));

        assert_recv(recv, &[0, 1, 2, 3]).await;
    }

    #[tokio::test]
    async fn feed_waker() {
        let (send, mut recv) = mpsc::channel(
            // Unlike tokio's mpsc channel, its capacity is equal to the sum of this argument and
            // the number of senders.
            0,
        );
        let [mut f0, mut f1] = fanin(send);

        assert_eq!(f0.feed(0).await, Ok(()));

        let f1_task = tokio::spawn(async move { f1.feed(1).await });
        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(f1_task.is_finished(), false);

        assert_eq!(recv.next().await, Some(0));
        assert_eq!(f1_task.await.unwrap(), Ok(()));
        assert_eq!(recv.next().await, Some(1));
    }

    #[tokio::test]
    async fn close() {
        let (send, mut recv) = mpsc::channel(10);
        let [mut f0, mut f1] = fanin(send);

        let recv_task = tokio::spawn(async move { recv.next().await });
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(recv_task.is_finished(), false);

        assert_eq!(f0.close().await, Ok(()));
        assert_eq!(recv_task.await.unwrap(), None);

        assert!(f1.send(1).await.unwrap_err().is_disconnected());
        assert_eq!(f1.close().await, Ok(()));
    }
}
