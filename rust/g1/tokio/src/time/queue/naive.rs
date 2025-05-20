use std::cmp::{Ordering, Reverse};
use std::collections::{BinaryHeap, VecDeque};
use std::time::Duration;

use tokio::time::{self, Instant};

#[derive(Clone, Debug)]
pub struct FixedDelayQueue<T> {
    // Use `VecDeque` because `delay` is fixed.
    queue: VecDeque<(T, Instant)>,
    delay: Duration,
}

#[derive(Clone, Debug)]
pub struct DelayQueue<T>(BinaryHeap<Reverse<Item<T>>>);

#[derive(Clone, Debug)]
struct Item<T>(T, Instant);

impl<T: PartialEq> PartialEq for FixedDelayQueue<T> {
    fn eq(&self, other: &Self) -> bool {
        self.iter().eq(other.iter())
    }
}

impl<T: Eq> Eq for FixedDelayQueue<T> {}

impl<T: PartialOrd> PartialOrd for FixedDelayQueue<T> {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        self.iter().partial_cmp(other.iter())
    }
}

impl<T: Ord> Ord for FixedDelayQueue<T> {
    fn cmp(&self, other: &Self) -> Ordering {
        self.iter().cmp(other.iter())
    }
}

//
// NOTE: We cannot implement `Eq` and `Ord` for `DelayQueue` as done above because
// `BinaryHeap::iter` traverses items in an arbitrary order.
//

impl<T> PartialEq for Item<T> {
    fn eq(&self, other: &Self) -> bool {
        self.1 == other.1
    }
}

impl<T> Eq for Item<T> {}

impl<T> PartialOrd for Item<T> {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.1.cmp(&other.1))
    }
}

impl<T> Ord for Item<T> {
    fn cmp(&self, other: &Self) -> Ordering {
        self.1.cmp(&other.1)
    }
}

//
// FixedDelayQueue
//

impl<T> Extend<T> for FixedDelayQueue<T> {
    fn extend<I>(&mut self, iter: I)
    where
        I: IntoIterator<Item = T>,
    {
        for value in iter {
            self.push(value);
        }
    }
}

impl<T> FixedDelayQueue<T> {
    pub fn new(delay: Duration) -> Self {
        Self {
            queue: VecDeque::new(),
            delay,
        }
    }

    pub fn with_capacity(delay: Duration, capacity: usize) -> Self {
        Self {
            queue: VecDeque::with_capacity(capacity),
            delay,
        }
    }

    pub fn delay(&self) -> Duration {
        self.delay
    }

    pub fn capacity(&self) -> usize {
        self.queue.capacity()
    }

    pub fn iter(&self) -> impl Iterator<Item = &T> {
        self.queue.iter().map(|(v, _)| v)
    }

    pub fn iter_mut(&mut self) -> impl Iterator<Item = &mut T> {
        self.queue.iter_mut().map(|(v, _)| v)
    }

    pub fn clear(&mut self) {
        self.queue.clear();
    }

    pub fn push(&mut self, value: T) {
        self.queue.push_back((value, Instant::now() + self.delay));
    }

    pub async fn pop(&mut self) -> Option<T> {
        time::sleep_until(self.queue.front()?.1).await;
        Some(self.queue.pop_front().unwrap().0)
    }
}

//
// DelayQueue
//

impl<T> Default for DelayQueue<T> {
    fn default() -> Self {
        Self::new()
    }
}

impl<T> Extend<(T, Duration)> for DelayQueue<T> {
    fn extend<I>(&mut self, iter: I)
    where
        I: IntoIterator<Item = (T, Duration)>,
    {
        for (value, delay) in iter {
            self.push(value, delay);
        }
    }
}

impl<T, const N: usize> From<[(T, Duration); N]> for DelayQueue<T> {
    fn from(arr: [(T, Duration); N]) -> Self {
        let mut queue = Self::with_capacity(N);
        queue.extend(arr);
        queue
    }
}

impl<T> FromIterator<(T, Duration)> for DelayQueue<T> {
    fn from_iter<I>(iter: I) -> Self
    where
        I: IntoIterator<Item = (T, Duration)>,
    {
        let mut queue = Self::new();
        queue.extend(iter);
        queue
    }
}

impl<T> DelayQueue<T> {
    pub fn new() -> Self {
        Self(BinaryHeap::new())
    }

    pub fn with_capacity(capacity: usize) -> Self {
        Self(BinaryHeap::with_capacity(capacity))
    }

    pub fn capacity(&self) -> usize {
        self.0.capacity()
    }

    // NOTE: This traverses items in an arbitrary order.
    pub fn iter(&self) -> impl Iterator<Item = &T> {
        self.0.iter().map(|Reverse(item)| &item.0)
    }

    pub fn clear(&mut self) {
        self.0.clear();
    }

    pub fn push(&mut self, value: T, delay: Duration) {
        self.0.push(Reverse(Item(value, Instant::now() + delay)));
    }

    pub async fn pop(&mut self) -> Option<T> {
        time::sleep_until(self.0.peek()?.0.1).await;
        Some(self.0.pop().unwrap().0.0)
    }
}

#[cfg(test)]
mod test_harness {
    use std::fmt;

    use super::*;

    impl<T> FixedDelayQueue<T>
    where
        T: Clone + fmt::Debug + PartialEq,
    {
        pub fn assert_queue(&self, expect: &[T]) {
            let values: Vec<_> = self.queue.iter().map(|(v, _)| v.clone()).collect();
            assert_eq!(values, expect);
            let delays: Vec<_> = self.queue.iter().map(|(_, d)| d).collect();
            assert!(delays.is_sorted(), "delays={:?}", delays);
        }
    }

    impl<T> DelayQueue<T>
    where
        T: Clone + fmt::Debug + PartialEq,
    {
        pub fn assert_queue(&self, expect: &[T]) {
            let values: Vec<_> = self
                .0
                .clone()
                .into_iter_sorted()
                .map(|Reverse(item)| item.0)
                .collect();
            assert_eq!(values, expect);
            let delays: Vec<_> = self
                .0
                .clone()
                .into_iter_sorted()
                .map(|Reverse(item)| item.1)
                .collect();
            assert!(delays.is_sorted(), "delays={:?}", delays);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn fixed_delay_queue() {
        let mut q1 = FixedDelayQueue::<u8>::new(Duration::from_secs(1));
        let mut q2 = FixedDelayQueue::with_capacity(Duration::from_secs(2), 4);
        assert_eq!(q1, q2);
        assert_ne!(q1.delay(), q2.delay());
        assert_ne!(q1.capacity(), q2.capacity());
        q1.assert_queue(&[]);
        q2.assert_queue(&[]);

        time::pause();
        q1.extend([1, 2]);
        q2.extend([1, 2, 3]);
        q1.assert_queue(&[1, 2]);
        q2.assert_queue(&[1, 2, 3]);
        assert!(q1 < q2);
        assert_ne!(q1, q2);

        time::advance(Duration::from_secs(1)).await;
        q1.push(3);
        q1.assert_queue(&[1, 2, 3]);
        q2.assert_queue(&[1, 2, 3]);
        assert_eq!(q1, q2);

        assert_eq!(q1.pop().await, Some(1));
        assert_eq!(q1.pop().await, Some(2));
        assert_eq!(q1.pop().await, Some(3));
        assert_eq!(q1.pop().await, None);
    }

    #[tokio::test]
    async fn delay_queue() {
        let mut q1 = DelayQueue::<u8>::new();
        let mut q2 = DelayQueue::with_capacity(4);
        assert_ne!(q1.capacity(), q2.capacity());
        q1.assert_queue(&[]);
        q2.assert_queue(&[]);

        time::pause();
        q1.push(1, Duration::from_secs(10));
        q2.push(1, Duration::from_secs(1));
        q2.push(2, Duration::from_secs(2));
        q2.push(3, Duration::from_secs(3));

        time::advance(Duration::from_secs(1)).await;
        q1.push(2, Duration::from_secs(8));

        time::advance(Duration::from_secs(1)).await;
        q1.push(3, Duration::from_secs(6));

        q1.assert_queue(&[3, 2, 1]);
        q2.assert_queue(&[1, 2, 3]);

        assert_eq!(q1.pop().await, Some(3));
        assert_eq!(q1.pop().await, Some(2));
        assert_eq!(q1.pop().await, Some(1));
        assert_eq!(q1.pop().await, None);
    }
}
