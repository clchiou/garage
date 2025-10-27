use std::borrow::Borrow;
use std::hash::Hash;
use std::iter::{self, FusedIterator};
use std::time::Duration;

use tokio::time::{self, Instant};

use g1_base::collections::HashOrderedMap;
use g1_base::collections::ordered::Entry;

#[derive(Clone, Debug)]
pub struct FixedDelaySet<T> {
    // Use `HashOrderedMap` because `delay` is fixed.
    set: HashOrderedMap<T, Instant>,
    delay: Duration,
}

pub type ExtractIf<'a, T, F>
    = impl FusedIterator<Item = T>
where
    T: 'a,
    F: FnMut(&T) -> bool;

impl<T: PartialEq> PartialEq for FixedDelaySet<T> {
    fn eq(&self, other: &Self) -> bool {
        self.iter().eq(other.iter())
    }
}

impl<T: Eq> Eq for FixedDelaySet<T> {}

//
// FixedDelaySet
//

impl<T> Extend<T> for FixedDelaySet<T>
where
    T: Eq + Hash,
{
    fn extend<I>(&mut self, iter: I)
    where
        I: IntoIterator<Item = T>,
    {
        let now = Instant::now();
        for value in iter {
            self.insert_now(value, now);
        }
    }
}

impl<T> FixedDelaySet<T> {
    pub fn new(delay: Duration) -> Self {
        Self {
            set: HashOrderedMap::new(),
            delay,
        }
    }

    pub fn with_capacity(delay: Duration, capacity: usize) -> Self {
        Self {
            set: HashOrderedMap::with_capacity(capacity),
            delay,
        }
    }

    pub fn delay(&self) -> Duration {
        self.delay
    }

    pub fn capacity(&self) -> usize {
        self.set.capacity()
    }

    pub fn iter(&self) -> impl Iterator<Item = &T> {
        self.set.keys()
    }

    #[define_opaque(ExtractIf)]
    pub fn extract_if<F>(&mut self, mut f: F) -> ExtractIf<'_, T, F>
    where
        F: FnMut(&T) -> bool,
    {
        self.set
            .extract_if(move |value, _| f(value))
            .map(|(value, _)| value)
    }

    pub fn retain<F>(&mut self, mut f: F)
    where
        F: FnMut(&T) -> bool,
    {
        self.set.retain(|value, _| f(value));
    }

    pub fn clear(&mut self) {
        self.set.clear();
    }

    pub async fn expired(&self) -> bool {
        let Some((_, deadline)) = self.set.front() else {
            return false;
        };
        time::sleep_until(*deadline).await;
        true
    }
}

impl<T> FixedDelaySet<T>
where
    T: Eq + Hash,
{
    pub fn contains<Q>(&self, value: &Q) -> bool
    where
        T: Borrow<Q>,
        Q: Hash + Eq + ?Sized,
    {
        self.set.contains_key(value)
    }

    pub fn insert(&mut self, value: T) -> bool {
        self.insert_now(value, Instant::now())
    }

    fn insert_now(&mut self, value: T, now: Instant) -> bool {
        self.set.insert_back(value, now + self.delay).is_none()
    }

    pub fn insert_new(&mut self, value: T) -> bool {
        let Entry::Vacant(entry) = self.set.entry(value) else {
            return false;
        };
        entry.insert(Instant::now() + self.delay);
        true
    }

    pub fn update<Q>(&mut self, value: &Q) -> bool
    where
        T: Borrow<Q>,
        Q: Hash + Eq + ?Sized,
    {
        let Some(deadline) = self.set.get_mut_back(value) else {
            return false;
        };
        *deadline = Instant::now() + self.delay;
        true
    }

    pub fn remove<Q>(&mut self, value: &Q) -> bool
    where
        T: Borrow<Q>,
        Q: Hash + Eq + ?Sized,
    {
        self.set.remove(value).is_some()
    }

    pub fn pop_expired(&mut self) -> Option<T> {
        self.pop_expired_now(Instant::now())
    }

    pub fn drain_expired(&mut self) -> impl Iterator<Item = T> {
        let now = Instant::now();
        iter::from_fn(move || self.pop_expired_now(now))
    }

    fn pop_expired_now(&mut self, now: Instant) -> Option<T> {
        let entry = self.set.front_entry()?;
        (entry.get() <= &now).then(|| entry.remove_entry().0)
    }

    pub fn clear_expired(&mut self) {
        let now = Instant::now();
        while let Some(entry) = self.set.front_entry() {
            if entry.get() <= &now {
                entry.remove();
            } else {
                break;
            }
        }
    }
}

#[cfg(test)]
mod test_harness {
    use std::fmt::Debug;

    use super::*;

    impl<T> FixedDelaySet<T>
    where
        T: Clone + Debug + PartialEq,
    {
        pub fn assert_set(&self, expect: &[T]) {
            let values: Vec<_> = self.set.iter().map(|(v, _)| v.clone()).collect();
            assert_eq!(values, expect);
            let delays: Vec<_> = self.set.iter().map(|(_, d)| d).collect();
            assert!(delays.is_sorted(), "delays={:?}", delays);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ms(millis: u64) -> Duration {
        Duration::from_millis(millis)
    }

    #[test]
    fn eq() {
        let mut s1 = FixedDelaySet::new(ms(1000));
        let mut s2 = FixedDelaySet::with_capacity(ms(2000), 4);
        assert_eq!(s1, s2);
        assert_ne!(s1.delay(), s2.delay());
        assert_ne!(s1.capacity(), s2.capacity());
        s1.assert_set(&[]);
        s2.assert_set(&[]);

        s1.extend([1, 2]);
        s2.extend([1, 2, 3]);
        s1.assert_set(&[1, 2]);
        s2.assert_set(&[1, 2, 3]);
        assert_ne!(s1, s2);

        assert_eq!(s1.insert(3), true);
        s1.assert_set(&[1, 2, 3]);
        assert_eq!(s1, s2);
    }

    #[test]
    fn extend() {
        let mut set = FixedDelaySet::new(ms(1000));
        set.extend([1, 2, 3]);
        set.assert_set(&[1, 2, 3]);
        let t1 = *set.set.get(&1).unwrap();
        let t2 = *set.set.get(&2).unwrap();
        let t3 = *set.set.get(&3).unwrap();
        assert_eq!(t1, t2);
        assert_eq!(t2, t3);

        let mut set = FixedDelaySet::new(ms(1000));
        set.insert(1);
        set.insert(2);
        set.insert(3);
        set.assert_set(&[1, 2, 3]);
        let t1 = *set.set.get(&1).unwrap();
        let t2 = *set.set.get(&2).unwrap();
        let t3 = *set.set.get(&3).unwrap();
        assert!(t1 < t2);
        assert!(t2 < t3);
    }

    #[tokio::test(start_paused = true)]
    async fn insert() {
        let mut set = FixedDelaySet::new(ms(1000));
        set.assert_set(&[]);

        let t0 = Instant::now();
        assert_eq!(set.insert(1), true);
        assert_eq!(set.insert(2), true);
        set.assert_set(&[1, 2]);
        assert_eq!(*set.set.get(&1).unwrap(), t0 + ms(1000));

        time::advance(ms(500)).await;

        assert_eq!(set.insert(1), false);
        set.assert_set(&[2, 1]);
        assert_eq!(*set.set.get(&1).unwrap(), t0 + ms(1500));
    }

    #[tokio::test(start_paused = true)]
    async fn insert_new() {
        let mut set = FixedDelaySet::new(ms(1000));
        set.assert_set(&[]);

        let t0 = Instant::now();
        assert_eq!(set.insert_new(1), true);
        assert_eq!(set.insert_new(2), true);
        set.assert_set(&[1, 2]);
        assert_eq!(*set.set.get(&1).unwrap(), t0 + ms(1000));

        time::advance(ms(500)).await;

        assert_eq!(set.insert_new(1), false);
        set.assert_set(&[1, 2]);
        assert_eq!(*set.set.get(&1).unwrap(), t0 + ms(1000));
    }

    #[tokio::test(start_paused = true)]
    async fn update() {
        let mut set = FixedDelaySet::new(ms(1000));
        set.assert_set(&[]);

        assert_eq!(set.update(&1), false);
        set.assert_set(&[]);

        let t0 = Instant::now();
        assert_eq!(set.insert(1), true);
        assert_eq!(set.insert(2), true);
        set.assert_set(&[1, 2]);
        assert_eq!(*set.set.get(&1).unwrap(), t0 + ms(1000));

        time::advance(ms(500)).await;

        assert_eq!(set.update(&1), true);
        set.assert_set(&[2, 1]);
        assert_eq!(*set.set.get(&1).unwrap(), t0 + ms(1500));
    }

    #[test]
    fn remove() {
        let mut set = FixedDelaySet::new(ms(1000));
        set.extend([1, 2]);
        set.assert_set(&[1, 2]);

        assert_eq!(set.remove(&1), true);
        set.assert_set(&[2]);

        assert_eq!(set.remove(&1), false);
        set.assert_set(&[2]);
    }

    #[tokio::test(start_paused = true)]
    async fn expired() {
        let mut set = FixedDelaySet::new(ms(1000));

        assert_eq!(set.expired().await, false);

        let t0 = Instant::now();
        assert_eq!(set.insert(1), true);
        time::advance(ms(500)).await;
        assert_eq!(set.insert(2), true);
        set.assert_set(&[1, 2]);

        assert_eq!(set.expired().await, true);
        assert_eq!(Instant::now(), t0 + ms(1000));
    }

    #[tokio::test(start_paused = true)]
    async fn pop_expired() {
        let mut set = FixedDelaySet::new(ms(1000));
        set.assert_set(&[]);

        assert_eq!(set.pop_expired(), None);
        set.assert_set(&[]);

        assert_eq!(set.insert(1), true);
        time::advance(ms(500)).await;
        assert_eq!(set.insert(2), true);
        set.assert_set(&[1, 2]);

        time::advance(ms(499)).await;
        assert_eq!(set.pop_expired(), None);
        set.assert_set(&[1, 2]);

        time::advance(ms(1)).await;
        assert_eq!(set.pop_expired(), Some(1));
        set.assert_set(&[2]);

        assert_eq!(set.pop_expired(), None);
        set.assert_set(&[2]);
    }

    #[tokio::test(start_paused = true)]
    async fn drain_expired() {
        let mut set = FixedDelaySet::new(ms(1000));
        set.assert_set(&[]);

        assert_eq!(set.drain_expired().collect::<Vec<_>>(), &[]);
        set.assert_set(&[]);

        assert_eq!(set.insert(1), true);
        time::advance(ms(300)).await;
        assert_eq!(set.insert(2), true);
        time::advance(ms(300)).await;
        assert_eq!(set.insert(3), true);
        set.assert_set(&[1, 2, 3]);

        time::advance(ms(399)).await;
        assert_eq!(set.drain_expired().collect::<Vec<_>>(), &[]);
        set.assert_set(&[1, 2, 3]);

        time::advance(ms(301)).await;
        assert_eq!(set.drain_expired().collect::<Vec<_>>(), &[1, 2]);
        set.assert_set(&[3]);

        assert_eq!(set.drain_expired().collect::<Vec<_>>(), &[]);
        set.assert_set(&[3]);
    }

    #[tokio::test(start_paused = true)]
    async fn clear_expired() {
        let mut set = FixedDelaySet::new(ms(1000));
        set.assert_set(&[]);

        set.clear_expired();
        set.assert_set(&[]);

        assert_eq!(set.insert(1), true);
        time::advance(ms(300)).await;
        assert_eq!(set.insert(2), true);
        time::advance(ms(300)).await;
        assert_eq!(set.insert(3), true);
        set.assert_set(&[1, 2, 3]);

        time::advance(ms(399)).await;
        set.clear_expired();
        set.assert_set(&[1, 2, 3]);

        time::advance(ms(301)).await;
        set.clear_expired();
        set.assert_set(&[3]);

        set.clear_expired();
        set.assert_set(&[3]);
    }
}
