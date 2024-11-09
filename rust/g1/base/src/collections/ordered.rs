//! Collection modeled after `OrderedDict` in Python.

use std::borrow::Borrow;
use std::fmt::{self, Debug};
use std::hash::{BuildHasher, Hash};
use std::mem;

use super::{
    index_map::{Entry, HashIndexMap, KeyAsHash},
    vec_list::{Cursor, VecList},
    DefaultHashBuilder,
};

#[derive(Clone)]
pub struct HashOrderedMap<K, V, S = DefaultHashBuilder> {
    map: HashIndexMap<Cursor, KeyAsHash, (K, V), K, S>,
    entries: VecList<(K, V)>,
}

pub type Keys<'a, K, V, S>
    = impl super::Iter<&'a K>
where
    K: 'a,
    V: 'a;

pub type Values<'a, K, V, S>
    = impl super::Iter<&'a V>
where
    K: 'a,
    V: 'a;

pub type ValuesMut<'a, K, V, S>
    = impl super::IterMut<&'a mut V>
where
    K: 'a,
    V: 'a;

pub type Iter<'a, K, V, S>
    = impl super::Iter<(&'a K, &'a V)>
where
    K: 'a,
    V: 'a;

pub type IterMut<'a, K, V, S>
    = impl super::IterMut<(&'a K, &'a mut V)>
where
    K: 'a,
    V: 'a;

impl<K, V, S> HashOrderedMap<K, V, S> {
    pub fn with_hasher(hash_builder: S) -> Self {
        Self {
            map: HashIndexMap::with_hasher(hash_builder),
            entries: VecList::new(),
        }
    }

    pub fn with_capacity_and_hasher(capacity: usize, hash_builder: S) -> Self {
        Self {
            map: HashIndexMap::with_capacity_and_hasher(capacity, hash_builder),
            entries: VecList::with_capacity(capacity),
        }
    }
}

impl<K, V, S> Default for HashOrderedMap<K, V, S>
where
    S: Default,
{
    fn default() -> Self {
        Self::with_hasher(Default::default())
    }
}

impl<K, V, S> HashOrderedMap<K, V, S>
where
    S: Default,
{
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_capacity(capacity: usize) -> Self {
        Self::with_capacity_and_hasher(capacity, Default::default())
    }
}

impl<K, V, S> Extend<(K, V)> for HashOrderedMap<K, V, S>
where
    K: Eq + Hash,
    S: BuildHasher,
{
    fn extend<I>(&mut self, iter: I)
    where
        I: IntoIterator<Item = (K, V)>,
    {
        for (k, v) in iter {
            self.insert(k, v);
        }
    }
}

impl<K, V, S, const N: usize> From<[(K, V); N]> for HashOrderedMap<K, V, S>
where
    K: Eq + Hash,
    S: BuildHasher + Default,
{
    fn from(arr: [(K, V); N]) -> Self {
        let mut map = Self::with_capacity(N);
        map.extend(arr);
        map
    }
}

impl<K, V, S> FromIterator<(K, V)> for HashOrderedMap<K, V, S>
where
    K: Eq + Hash,
    S: BuildHasher + Default,
{
    fn from_iter<I>(iter: I) -> Self
    where
        I: IntoIterator<Item = (K, V)>,
    {
        let mut map = Self::default();
        map.extend(iter);
        map
    }
}

impl<K, V, S> Debug for HashOrderedMap<K, V, S>
where
    K: Debug,
    V: Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_map().entries(self.iter()).finish()
    }
}

/// Partial equality.
///
/// NOTE: `OrderedDict.__eq__` in Python is order-sensitive, and we adhere to that behavior here.
impl<K, V, S> PartialEq for HashOrderedMap<K, V, S>
where
    K: PartialEq,
    V: PartialEq,
{
    fn eq(&self, other: &Self) -> bool {
        self.entries == other.entries
    }
}

impl<K, V, S> HashOrderedMap<K, V, S>
where
    K: Eq + Hash,
    V: PartialEq,
    S: BuildHasher,
{
    pub fn eq_ignore_order(&self, other: &Self) -> bool {
        self.len() == other.len()
            && self
                .iter()
                .all(|(key, value)| other.get(key).map_or(false, |v| v == value))
    }
}

impl<K, V, S> Eq for HashOrderedMap<K, V, S>
where
    K: Eq,
    V: Eq,
{
}

impl<K, V, S> HashOrderedMap<K, V, S> {
    pub fn capacity(&self) -> usize {
        self.map.capacity()
    }

    pub fn is_empty(&self) -> bool {
        self.map.is_empty()
    }

    pub fn len(&self) -> usize {
        self.map.len()
    }

    pub fn clear(&mut self) {
        self.map.clear();
        self.entries.clear();
    }
}

impl<K, V, S> HashOrderedMap<K, V, S> {
    pub fn keys(&self) -> Keys<'_, K, V, S> {
        self.entries.iter().map(|(k, _)| k)
    }

    pub fn values(&self) -> Values<'_, K, V, S> {
        self.entries.iter().map(|(_, v)| v)
    }

    pub fn values_mut(&mut self) -> ValuesMut<'_, K, V, S> {
        self.entries.iter_mut().map(|(_, v)| v)
    }

    pub fn iter(&self) -> Iter<'_, K, V, S> {
        self.entries.iter().map(|(k, v)| (k, v))
    }

    pub fn iter_mut(&mut self) -> IterMut<'_, K, V, S> {
        self.entries.iter_mut().map(|(k, v)| (&*k, v))
    }
}

impl<K, V, S> HashOrderedMap<K, V, S>
where
    K: Eq + Hash,
    S: BuildHasher,
{
    pub fn contains_key<Q>(&self, key: &Q) -> bool
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.map.get(&self.entries, key).is_some()
    }

    pub fn get<Q>(&self, key: &Q) -> Option<&V>
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.map.get(&self.entries, key).map(|p| &self.entries[p].1)
    }

    pub fn get_mut<Q>(&mut self, key: &Q) -> Option<&mut V>
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.map
            .get(&self.entries, key)
            .map(|p| &mut self.entries[p].1)
    }

    /// Similar to `get_mut`, but moves the entry to the back.
    pub fn get_mut_back<Q>(&mut self, key: &Q) -> Option<&mut V>
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.map.get(&self.entries, key).map(|p| {
            self.entries.move_back(p);
            &mut self.entries[p].1
        })
    }

    // TODO: Provide an `entry` method equivalent to `HashMap::entry`.
    pub fn get_or_insert_with<F>(&mut self, key: K, default: F) -> &mut V
    where
        F: FnOnce() -> V,
    {
        let p = *self
            .map
            .entry(&self.entries, &key)
            .or_insert_with(|| self.entries.push_back((key, default())))
            .get();
        &mut self.entries[p].1
    }

    /// Similar to `get_or_insert_with`, but moves the entry to the back.
    pub fn get_or_insert_with_back<F>(&mut self, key: K, default: F) -> &mut V
    where
        F: FnOnce() -> V,
    {
        let p = *self
            .map
            .entry(&self.entries, &key)
            .and_modify(|&mut p| self.entries.move_back(p))
            .or_insert_with(|| self.entries.push_back((key, default())))
            .get();
        &mut self.entries[p].1
    }

    pub fn insert(&mut self, key: K, value: V) -> Option<V> {
        self.insert_then_move(key, value, false)
    }

    /// Similar to `insert`, but moves the entry (existing or otherwise) to the back.
    pub fn insert_back(&mut self, key: K, value: V) -> Option<V> {
        self.insert_then_move(key, value, true)
    }

    fn insert_then_move(&mut self, key: K, value: V, move_entry: bool) -> Option<V> {
        match self.map.entry(&self.entries, &key) {
            Entry::Occupied(entry) => {
                let p = *entry.get();
                if move_entry {
                    self.entries.move_back(p);
                }
                Some(mem::replace(&mut self.entries[p].1, value))
            }
            Entry::Vacant(entry) => {
                entry.insert(self.entries.push_back((key, value)));
                None
            }
        }
    }

    pub fn remove<Q>(&mut self, key: &Q) -> Option<V>
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        let p = self.map.remove(&self.entries, key)?;
        Some(self.entries.remove(p).1)
    }

    pub fn move_front<Q>(&mut self, key: &Q) -> bool
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        let Some(p) = self.map.get(&self.entries, key) else {
            return false;
        };
        self.entries.move_front(p);
        true
    }

    pub fn move_back<Q>(&mut self, key: &Q) -> bool
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        let Some(p) = self.map.get(&self.entries, key) else {
            return false;
        };
        self.entries.move_back(p);
        true
    }

    pub fn pop_front(&mut self) -> Option<(K, V)> {
        let key = &self.entries.front()?.0;
        assert!(self.map.remove(&self.entries, key).is_some());
        self.entries.pop_front()
    }

    pub fn pop_back(&mut self) -> Option<(K, V)> {
        let key = &self.entries.back()?.0;
        assert!(self.map.remove(&self.entries, key).is_some());
        self.entries.pop_back()
    }
}

#[cfg(test)]
mod test_harness {
    use crate::iter::IteratorExt;

    use super::*;

    impl HashOrderedMap<char, usize> {
        pub fn assert_map(&mut self, expect: &[(char, usize)]) {
            assert_eq!(self.is_empty(), expect.is_empty());
            assert_eq!(self.len(), expect.len());

            assert_eq!(
                self.keys().collect::<Vec<_>>(),
                expect.iter().map(|(k, _)| k).collect::<Vec<_>>(),
            );
            assert_eq!(
                self.values().collect::<Vec<_>>(),
                expect.iter().map(|(_, v)| v).collect::<Vec<_>>(),
            );
            assert_eq!(
                self.values_mut().map(|v| &*v).collect::<Vec<_>>(),
                expect.iter().map(|(_, v)| v).collect::<Vec<_>>(),
            );
            assert_eq!(
                self.iter().collect::<Vec<_>>(),
                expect.iter().map(|(k, v)| (k, v)).collect::<Vec<_>>(),
            );
            assert_eq!(
                self.iter_mut().map(|(k, v)| (&*k, &*v)).collect::<Vec<_>>(),
                expect.iter().map(|(k, v)| (k, v)).collect::<Vec<_>>(),
            );

            for (k, v) in expect {
                assert_eq!(self.contains_key(k), true);
                assert_eq!(self.get(k), Some(v));
                assert_eq!(self.get_mut(k).map(|v| &*v), Some(v));
            }

            assert_eq!(self.map.len(), self.entries.len());

            let mut cursors = Vec::with_capacity(self.len());
            let mut p = self.entries.cursor_front();
            while let Some(cursor) = p {
                cursors.push(usize::from(cursor));
                p = self.entries.next(cursor);
            }
            cursors.sort();
            assert_eq!(
                self.map.iter().map(usize::from).collect_then_sort(),
                cursors,
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new() {
        let mut map1 = HashOrderedMap::new();
        map1.assert_map(&[]);
        assert_eq!(map1.capacity(), 0);

        let mut map2 = HashOrderedMap::with_capacity(4);
        map2.assert_map(&[]);
        assert_ne!(map2.capacity(), 0);

        assert_eq!(map1, map2);
        assert_ne!(map1.capacity(), map2.capacity());

        HashOrderedMap::default().assert_map(&[]);

        let expect = [('a', 100)];
        HashOrderedMap::from(expect).assert_map(&expect);
        HashOrderedMap::from_iter(expect).assert_map(&expect);
        let expect = [('a', 100), ('c', 102)];
        HashOrderedMap::from(expect).assert_map(&expect);
        HashOrderedMap::from_iter(expect).assert_map(&expect);
        let expect = [('a', 100), ('c', 102), ('b', 101)];
        HashOrderedMap::from(expect).assert_map(&expect);
        HashOrderedMap::from_iter(expect).assert_map(&expect);
    }

    #[test]
    fn eq() {
        let map1 = HashOrderedMap::<char, usize>::from([('a', 100), ('b', 101)]);

        let map2 = HashOrderedMap::from([('b', 101), ('a', 100)]);
        assert_ne!(map1, map2);
        assert_eq!(map1.eq_ignore_order(&map2), true);

        assert_ne!(map1, HashOrderedMap::from([('a', 100)]));
        assert_ne!(map1, HashOrderedMap::from([('a', 101), ('b', 100)]));
    }

    #[test]
    fn clear() {
        let mut map = HashOrderedMap::from([('a', 100), ('b', 101)]);
        map.assert_map(&[('a', 100), ('b', 101)]);

        map.clear();
        map.assert_map(&[]);
    }

    #[test]
    fn contains_and_get() {
        let mut map = HashOrderedMap::from([('a', 100), ('b', 101)]);
        map.assert_map(&[('a', 100), ('b', 101)]);

        assert_eq!(map.contains_key(&'a'), true);
        assert_eq!(map.contains_key(&'b'), true);
        assert_eq!(map.contains_key(&'c'), false);

        assert_eq!(map.get(&'a'), Some(&100));
        assert_eq!(map.get(&'b'), Some(&101));
        assert_eq!(map.get(&'c'), None);

        assert_eq!(map.get_mut(&'a'), Some(&mut 100));
        assert_eq!(map.get_mut(&'b'), Some(&mut 101));
        assert_eq!(map.get_mut(&'c'), None);

        map.assert_map(&[('a', 100), ('b', 101)]);

        assert_eq!(map.get_mut_back(&'a'), Some(&mut 100));
        map.assert_map(&[('b', 101), ('a', 100)]);
        assert_eq!(map.get_mut_back(&'b'), Some(&mut 101));
        map.assert_map(&[('a', 100), ('b', 101)]);
        assert_eq!(map.get_mut_back(&'c'), None);
        map.assert_map(&[('a', 100), ('b', 101)]);
    }

    #[test]
    fn get_or_insert_with() {
        let mut map = HashOrderedMap::new();
        map.assert_map(&[]);

        assert_eq!(map.get_or_insert_with('a', || 100), &mut 100);
        map.assert_map(&[('a', 100)]);
        assert_eq!(map.get_or_insert_with('b', || 101), &mut 101);
        map.assert_map(&[('a', 100), ('b', 101)]);

        assert_eq!(map.get_or_insert_with('a', || 102), &mut 100);
        map.assert_map(&[('a', 100), ('b', 101)]);
    }

    #[test]
    fn get_or_insert_with_back() {
        let mut map = HashOrderedMap::new();
        map.assert_map(&[]);

        assert_eq!(map.get_or_insert_with_back('a', || 100), &mut 100);
        map.assert_map(&[('a', 100)]);
        assert_eq!(map.get_or_insert_with_back('b', || 101), &mut 101);
        map.assert_map(&[('a', 100), ('b', 101)]);

        assert_eq!(map.get_or_insert_with_back('a', || 102), &mut 100);
        map.assert_map(&[('b', 101), ('a', 100)]);
    }

    #[test]
    fn insert() {
        let mut map = HashOrderedMap::new();
        map.assert_map(&[]);

        assert_eq!(map.insert('a', 100), None);
        map.assert_map(&[('a', 100)]);
        assert_eq!(map.insert('b', 101), None);
        map.assert_map(&[('a', 100), ('b', 101)]);

        assert_eq!(map.insert('a', 102), Some(100));
        map.assert_map(&[('a', 102), ('b', 101)]);
    }

    #[test]
    fn insert_back() {
        let mut map = HashOrderedMap::new();
        map.assert_map(&[]);

        assert_eq!(map.insert_back('a', 100), None);
        map.assert_map(&[('a', 100)]);
        assert_eq!(map.insert_back('b', 101), None);
        map.assert_map(&[('a', 100), ('b', 101)]);

        assert_eq!(map.insert_back('a', 102), Some(100));
        map.assert_map(&[('b', 101), ('a', 102)]);
    }

    #[test]
    fn remove() {
        let mut map = HashOrderedMap::from([('a', 100), ('b', 101), ('c', 102)]);
        map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);

        assert_eq!(map.remove(&'b'), Some(101));
        map.assert_map(&[('a', 100), ('c', 102)]);
        assert_eq!(map.remove(&'b'), None);
        map.assert_map(&[('a', 100), ('c', 102)]);
    }

    #[test]
    fn move_front() {
        let mut map = HashOrderedMap::from([('a', 100), ('b', 101), ('c', 102)]);
        map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);

        for _ in 0..3 {
            assert_eq!(map.move_front(&'b'), true);
            map.assert_map(&[('b', 101), ('a', 100), ('c', 102)]);
        }

        assert_eq!(map.move_front(&'d'), false);
        map.assert_map(&[('b', 101), ('a', 100), ('c', 102)]);
    }

    #[test]
    fn move_back() {
        let mut map = HashOrderedMap::from([('a', 100), ('b', 101), ('c', 102)]);
        map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);

        for _ in 0..3 {
            assert_eq!(map.move_back(&'b'), true);
            map.assert_map(&[('a', 100), ('c', 102), ('b', 101)]);
        }

        assert_eq!(map.move_back(&'d'), false);
        map.assert_map(&[('a', 100), ('c', 102), ('b', 101)]);
    }

    #[test]
    fn pop_front() {
        let mut map = HashOrderedMap::from([('a', 100), ('b', 101), ('c', 102)]);
        map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);

        assert_eq!(map.pop_front(), Some(('a', 100)));
        map.assert_map(&[('b', 101), ('c', 102)]);
        assert_eq!(map.pop_front(), Some(('b', 101)));
        map.assert_map(&[('c', 102)]);
        assert_eq!(map.pop_front(), Some(('c', 102)));
        map.assert_map(&[]);

        assert_eq!(map.pop_front(), None);
        map.assert_map(&[]);
    }

    #[test]
    fn pop_back() {
        let mut map = HashOrderedMap::from([('a', 100), ('b', 101), ('c', 102)]);
        map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);

        assert_eq!(map.pop_back(), Some(('c', 102)));
        map.assert_map(&[('a', 100), ('b', 101)]);
        assert_eq!(map.pop_back(), Some(('b', 101)));
        map.assert_map(&[('a', 100)]);
        assert_eq!(map.pop_back(), Some(('a', 100)));
        map.assert_map(&[]);

        assert_eq!(map.pop_back(), None);
        map.assert_map(&[]);
    }
}
