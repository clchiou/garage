use std::collections::VecDeque;
use std::pin::Pin;
use std::sync::{Arc, Mutex};
use std::task::{Context, Poll, Waker};

use futures::stream;

use g1_base::{sync::MutexExt, task};

/// Splits the input stream into forks.
///
/// Note that forks are leaky; if they fall behind, they will drop older items.
pub fn fork<const N: usize, Stream, Predicate, Item>(
    stream: Stream,
    forks: [(Predicate, usize); N],
) -> [Fork<Stream, Predicate, Item>; N] {
    let inner = Arc::new(Mutex::new(Inner::new(stream, forks)));
    // We use `Vec`-copying because Rust currently cannot transmute from
    // `[MaybeUninit<Fork<..>>; N]` to `[Fork<..>; N]`.
    let mut forks = Vec::with_capacity(N);
    for index in 0..N {
        forks.push(Fork::new(inner.clone(), index));
    }
    // We do not call `unwrap` because it requires `Debug`.
    match forks.try_into() {
        Ok(forks) => forks,
        Err(_) => std::unreachable!(),
    }
}

#[derive(Debug)]
pub struct Fork<Stream, Predicate, Item> {
    inner: Arc<Mutex<Inner<Stream, Predicate, Item>>>,
    index: usize,
}

#[derive(Debug)]
struct Inner<Stream, Predicate, Item> {
    stream: Stream,
    eof: bool,
    queues: Vec<Queue<Predicate, Item>>,
}

#[derive(Debug)]
struct Queue<Predicate, Item> {
    predicate: Predicate,
    queue: VecDeque<Item>,
    queue_size: usize,

    waker: Option<Waker>,
}

impl<Stream, Predicate, Item> Fork<Stream, Predicate, Item> {
    fn new(inner: Arc<Mutex<Inner<Stream, Predicate, Item>>>, index: usize) -> Self {
        Self { inner, index }
    }
}

impl<Stream, Predicate, Item> stream::Stream for Fork<Stream, Predicate, Item>
where
    Stream: stream::Stream<Item = Item> + Unpin,
    Predicate: FnMut(&Item) -> bool,
{
    type Item = Item;

    fn poll_next(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        let this = self.get_mut();
        let mut inner = this.inner.must_lock();

        if inner.eof {
            return Poll::Ready(inner.queues[this.index].pop());
        }

        let mut should_wake = false;
        while let Poll::Ready(item) = Pin::new(&mut inner.stream).poll_next(context) {
            should_wake = true;
            match item {
                Some(item) => {
                    for queue in &mut inner.queues {
                        if (queue.predicate)(&item) {
                            queue.push(item);
                            break;
                        }
                    }
                }
                None => {
                    inner.eof = true;
                    break;
                }
            }
        }
        if should_wake {
            for queue in &mut inner.queues {
                queue.wake();
            }
        }

        match inner.queues[this.index].pop() {
            item @ Some(_) => Poll::Ready(item),
            _ => {
                if inner.eof {
                    Poll::Ready(None)
                } else {
                    inner.queues[this.index].update_waker(context);
                    Poll::Pending
                }
            }
        }
    }

    fn size_hint(&self) -> (usize, Option<usize>) {
        let (_, upper_bound) = self.inner.must_lock().stream.size_hint();
        (0, upper_bound)
    }
}

impl<Stream, Predicate, Item> Inner<Stream, Predicate, Item> {
    fn new<const N: usize>(stream: Stream, forks: [(Predicate, usize); N]) -> Self {
        Self {
            stream,
            eof: false,
            queues: forks
                .into_iter()
                .map(|(predicate, queue_size)| Queue::new(predicate, queue_size))
                .collect(),
        }
    }
}

impl<Predicate, Item> Queue<Predicate, Item> {
    fn new(predicate: Predicate, queue_size: usize) -> Self {
        assert!(queue_size > 0); // `push` requires this.
        Self {
            predicate,
            queue: VecDeque::with_capacity(queue_size),
            queue_size,
            waker: None,
        }
    }

    fn push(&mut self, item: Item) {
        let size = self.queue.len();
        if size >= self.queue_size {
            tracing::warn!(size, "fork queue full");
            self.queue.pop_front();
        }
        self.queue.push_back(item);
    }

    fn pop(&mut self) -> Option<Item> {
        self.queue.pop_front()
    }

    fn update_waker(&mut self, context: &Context) {
        task::update_waker(&mut self.waker, context);
    }

    fn wake(&mut self) {
        if let Some(waker) = self.waker.take() {
            waker.wake();
        }
    }
}

#[cfg(test)]
mod tests {
    use std::fmt;
    use std::time::Duration;

    use futures::{
        channel::mpsc,
        sink::SinkExt,
        stream::{Stream as _, StreamExt},
    };
    use tokio::time;

    use super::*;

    const N: usize = 10;

    fn new_forks<Stream>(stream: Stream) -> [Fork<Stream, fn(&usize) -> bool, usize>; 2] {
        fork(stream, [(is_odd, N), (is_even, N)])
    }

    fn is_odd(x: &usize) -> bool {
        x % 2 == 1
    }

    fn is_even(x: &usize) -> bool {
        !is_odd(x)
    }

    fn to_odds(n: usize) -> Vec<usize> {
        (0..n).into_iter().map(|x| x * 2 + 1).collect()
    }

    fn to_evens(n: usize) -> Vec<usize> {
        (0..n).into_iter().map(|x| x * 2).collect()
    }

    async fn assert_stream<Stream, Item>(mut stream: Stream, expect: &[Item])
    where
        Stream: stream::Stream<Item = Item> + Unpin,
        Item: fmt::Debug + PartialEq,
    {
        let mut items = Vec::with_capacity(expect.len());
        while let Some(item) = stream.next().await {
            items.push(item);
        }
        assert_eq!(items, expect);
    }

    #[tokio::test]
    async fn test_fork() {
        let [odd, even] = new_forks(stream::empty());
        assert_eq!(odd.size_hint(), (0, Some(0)));
        assert_eq!(even.size_hint(), (0, Some(0)));
        assert_stream(odd, &[]).await;
        assert_stream(even, &[]).await;

        let [odd, even] = new_forks(stream::iter(0..3));
        assert_eq!(odd.size_hint(), (0, Some(3)));
        assert_eq!(even.size_hint(), (0, Some(3)));
        assert_stream(odd, &[1]).await;
        assert_stream(even, &[0, 2]).await;

        let [odd, even] = new_forks(stream::iter(0..N * 2));
        assert_eq!(odd.size_hint(), (0, Some(N * 2)));
        assert_eq!(even.size_hint(), (0, Some(N * 2)));
        assert_stream(odd, &to_odds(N)).await;
        assert_stream(even, &to_evens(N)).await;

        // Items get dropped.
        let [odd, even] = new_forks(stream::iter(0..N * 2 + 1));
        assert_eq!(odd.size_hint(), (0, Some(N * 2 + 1)));
        assert_eq!(even.size_hint(), (0, Some(N * 2 + 1)));
        assert_stream(odd, &to_odds(N)).await;
        assert_stream(even, &to_evens(N + 1)[1..]).await;

        // Items get dropped.
        let [odd, even] = new_forks(stream::iter(0..N * 4));
        assert_eq!(odd.size_hint(), (0, Some(N * 4)));
        assert_eq!(even.size_hint(), (0, Some(N * 4)));
        assert_stream(odd, &to_odds(N * 2)[N..]).await;
        assert_stream(even, &to_evens(N * 2)[N..]).await;

        // Items are sent to the first-matching fork.
        let [f0, f1] = fork(stream::iter(0..4), [(is_odd, N), (is_odd, N)]);
        assert_eq!(f0.size_hint(), (0, Some(4)));
        assert_eq!(f1.size_hint(), (0, Some(4)));
        assert_stream(f0, &[1, 3]).await;
        assert_stream(f1, &[]).await;

        // Items are sent to none of the forks.
        let [f0, f1] = fork(stream::iter([2, 4, 6]), [(is_odd, N), (is_odd, N)]);
        assert_eq!(f0.size_hint(), (0, Some(3)));
        assert_eq!(f1.size_hint(), (0, Some(3)));
        assert_stream(f0, &[]).await;
        assert_stream(f1, &[]).await;
    }

    #[tokio::test]
    async fn fork_waker() {
        for items in [&[0usize, 1], &[1, 0]] {
            let (mut send, recv) = mpsc::channel(N);
            let [mut odd, mut even] = new_forks(recv);

            let odd_task = tokio::spawn(async move { odd.next().await });
            // TODO: Can we write this test without using `time::sleep`?
            time::sleep(Duration::from_millis(10)).await;

            let even_task = tokio::spawn(async move { even.next().await });
            time::sleep(Duration::from_millis(10)).await;

            // `odd_task` is blocked before `even_task`, but both should be awakened here
            // regardless of the order of items.
            for item in items {
                let _ = send.send(*item).await;
            }

            assert_eq!(odd_task.await.unwrap(), Some(1));
            assert_eq!(even_task.await.unwrap(), Some(0));
        }

        {
            let (mut send, recv) = mpsc::channel(N);
            let [mut odd, _] = new_forks(recv);

            let _ = send.send(0).await;

            let odd_task = tokio::spawn(async move { odd.next().await });
            time::sleep(Duration::from_millis(10)).await;
            assert_eq!(odd_task.is_finished(), false);

            let _ = send.send(1).await;
            assert_eq!(odd_task.await.unwrap(), Some(1));
        }
    }
}
