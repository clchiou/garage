use std::borrow::Borrow;
use std::cmp::{Ord, Reverse};
use std::collections::BinaryHeap;
use std::hash::Hash;
use std::mem;
use std::time::{Duration, Instant};

use crate::collections::HashOrderedMap;

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct Stat {
    pub num_hits: u64,
    pub num_misses: u64,
    // Number of cache misses that could have been avoided if `timeout` had been longer.
    pub num_expires: u64,
}

impl Stat {
    pub fn new(num_hits: u64, num_misses: u64, num_expires: u64) -> Self {
        Self {
            num_hits,
            num_misses,
            num_expires,
        }
    }
}

#[derive(Debug)]
pub struct LruCache<K, V> {
    entries: HashOrderedMap<K, Entry<V>>,
    max_size: usize,

    possible_deadlines: BinaryHeap<Reverse<(Instant, K)>>,
    timeout: Option<Duration>,

    stat: Stat,
}

#[derive(Debug)]
struct Entry<V> {
    value: V,
    deadline: Option<Instant>,
}

impl<K, V> LruCache<K, V>
where
    K: Ord,
{
    pub fn new(max_size: usize, timeout: Option<Duration>) -> Self {
        Self {
            entries: HashOrderedMap::with_capacity(max_size),
            max_size,

            possible_deadlines: BinaryHeap::new(),
            timeout,

            stat: Default::default(),
        }
    }
}

impl<K, V> LruCache<K, V> {
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn clear(&mut self) {
        self.entries.clear();
        self.possible_deadlines.clear();
    }

    pub fn take_stat(&mut self) -> Stat {
        mem::take(&mut self.stat)
    }
}

impl<K, V> LruCache<K, V>
where
    K: Eq + Hash,
    K: Ord,
    K: Clone, // `insert` needs this.
{
    pub fn get<Q>(&mut self, key: &Q) -> Option<&mut V>
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        let Some(entry) = self.entries.get_mut_back(key) else {
            self.stat.num_misses += 1;
            return None;
        };
        if entry.is_expired(Instant::now()) {
            self.stat.num_expires += 1;
            None
        } else {
            self.stat.num_hits += 1;
            Some(&mut entry.value)
        }
    }

    pub fn insert(&mut self, key: K, value: V) {
        let now = Instant::now();
        let deadline = self.timeout.map(|t| now + t);
        self.entries
            .insert_back(key.clone(), Entry { value, deadline });
        if let Some(deadline) = deadline {
            self.possible_deadlines.push(Reverse((deadline, key)));
        }

        self.evict(now);
    }

    pub fn remove<Q>(&mut self, key: &Q) -> Option<V>
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.entries.remove(key).map(|e| e.value)
    }

    fn evict(&mut self, now: Instant) {
        // When the cache is full, expired entries should be removed before eviction.
        while let Some(Reverse((deadline, key))) = self.possible_deadlines.peek() {
            if now <= *deadline {
                break;
            }

            let expired = self.entries.get(key).is_some_and(|e| e.is_expired(now));
            if expired {
                self.entries.remove(key);
            }

            self.possible_deadlines.pop();
        }

        while self.entries.len() > self.max_size {
            self.entries.pop_front();
        }
    }
}

impl<V> Entry<V> {
    fn is_expired(&self, now: Instant) -> bool {
        self.deadline.is_some_and(|deadline| deadline < now)
    }
}

#[cfg(test)]
mod tests {
    use std::thread;

    use super::*;

    fn assert_cache(
        cache: &LruCache<u8, u8>,
        entries: &[(u8, u8)],
        possible_deadlines: &[u8],
        num_hits: u64,
        num_misses: u64,
        num_expires: u64,
    ) {
        assert_eq!(
            cache
                .entries
                .iter()
                .map(|(k, v)| (*k, v.value))
                .collect::<Vec<_>>(),
            entries,
        );
        assert_eq!(
            cache
                .possible_deadlines
                .iter()
                .map(|Reverse((_, k))| *k)
                .collect::<Vec<_>>(),
            possible_deadlines,
        );
        assert_eq!(cache.stat.num_hits, num_hits);
        assert_eq!(cache.stat.num_misses, num_misses);
        assert_eq!(cache.stat.num_expires, num_expires);
    }

    #[test]
    fn get() {
        let mut cache = LruCache::new(3, None);
        assert_cache(&cache, &[], &[], 0, 0, 0);

        assert_eq!(cache.get(&1), None);
        assert_cache(&cache, &[], &[], 0, 1, 0);

        assert_eq!(cache.get(&2), None);
        assert_cache(&cache, &[], &[], 0, 2, 0);

        assert_eq!(cache.take_stat(), Stat::new(0, 2, 0));
        assert_cache(&cache, &[], &[], 0, 0, 0);

        let mut cache = LruCache::new(3, None);
        const E1: (u8, u8) = (1, 10);
        const E2: (u8, u8) = (2, 20);
        const E3: (u8, u8) = (3, 30);
        cache.insert(1, 10);
        cache.insert(2, 20);
        cache.insert(3, 30);
        assert_cache(&cache, &[E1, E2, E3], &[], 0, 0, 0);

        assert_eq!(cache.get(&1), Some(&mut 10));
        assert_cache(&cache, &[E2, E3, E1], &[], 1, 0, 0);

        assert_eq!(cache.get(&3), Some(&mut 30));
        assert_cache(&cache, &[E2, E1, E3], &[], 2, 0, 0);

        assert_eq!(cache.get(&2), Some(&mut 20));
        assert_cache(&cache, &[E1, E3, E2], &[], 3, 0, 0);

        assert_eq!(cache.get(&4), None);
        assert_cache(&cache, &[E1, E3, E2], &[], 3, 1, 0);

        assert_eq!(cache.take_stat(), Stat::new(3, 1, 0));
        assert_cache(&cache, &[E1, E3, E2], &[], 0, 0, 0);
    }

    // TODO: Could we test this without `thread::sleep`?
    #[test]
    fn get_expired() {
        let mut cache = LruCache::new(3, Some(Duration::from_millis(10)));
        cache.insert(1, 10);
        assert_cache(&cache, &[(1, 10)], &[1], 0, 0, 0);

        assert_eq!(cache.get(&1), Some(&mut 10));
        assert_cache(&cache, &[(1, 10)], &[1], 1, 0, 0);

        thread::sleep(Duration::from_millis(20));

        // `get` does not remove expired entries.
        assert_eq!(cache.get(&1), None);
        assert_cache(&cache, &[(1, 10)], &[1], 1, 0, 1);
        assert_eq!(cache.get(&1), None);
        assert_cache(&cache, &[(1, 10)], &[1], 1, 0, 2);

        cache.insert(2, 20); // Evict!
        assert_cache(&cache, &[(2, 20)], &[2], 1, 0, 2);
    }

    #[test]
    fn insert() {
        let mut cache = LruCache::new(3, None);
        assert_cache(&cache, &[], &[], 0, 0, 0);

        cache.insert(1, 10);
        assert_cache(&cache, &[(1, 10)], &[], 0, 0, 0);

        cache.insert(2, 20);
        assert_cache(&cache, &[(1, 10), (2, 20)], &[], 0, 0, 0);

        cache.insert(3, 30);
        assert_cache(&cache, &[(1, 10), (2, 20), (3, 30)], &[], 0, 0, 0);

        cache.insert(1, 11);
        assert_cache(&cache, &[(2, 20), (3, 30), (1, 11)], &[], 0, 0, 0);

        cache.insert(3, 31);
        assert_cache(&cache, &[(2, 20), (1, 11), (3, 31)], &[], 0, 0, 0);
    }

    #[test]
    fn evict() {
        let mut cache = LruCache::new(3, None);
        cache.insert(1, 10);
        cache.insert(2, 20);
        cache.insert(3, 30);
        assert_cache(&cache, &[(1, 10), (2, 20), (3, 30)], &[], 0, 0, 0);

        cache.insert(4, 40);
        assert_cache(&cache, &[(2, 20), (3, 30), (4, 40)], &[], 0, 0, 0);

        cache.insert(5, 50);
        assert_cache(&cache, &[(3, 30), (4, 40), (5, 50)], &[], 0, 0, 0);
    }

    // TODO: Could we test this without `thread::sleep`?
    #[test]
    fn evict_expired() {
        let mut cache = LruCache::new(10, Some(Duration::from_millis(10)));
        cache.insert(1, 10);
        cache.insert(2, 20);
        cache.insert(3, 30);
        assert_cache(&cache, &[(1, 10), (2, 20), (3, 30)], &[1, 2, 3], 0, 0, 0);

        thread::sleep(Duration::from_millis(20));

        cache.insert(1, 11);
        assert_cache(&cache, &[(1, 11)], &[1], 0, 0, 0);
    }

    #[test]
    fn is_expired() {
        fn test(deadline: Option<Instant>, now: Instant, expect: bool) {
            assert_eq!(
                Entry {
                    value: (),
                    deadline,
                }
                .is_expired(now),
                expect,
            );
        }

        let t0 = Instant::now();
        let t1 = t0 + Duration::from_secs(1);

        test(None, t0, false);

        test(Some(t0), t0, false);
        test(Some(t1), t0, false);

        test(Some(t0), t1, true);
    }
}
