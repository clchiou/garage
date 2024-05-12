//! Collection modeled after `BiMap` in Java Guava library.

use std::borrow::Borrow;
use std::fmt::{self, Debug};
use std::hash::{BuildHasher, Hash};

use super::{bitable::HashBasedBiTable, DefaultHashBuilder};

#[derive(Clone)]
pub struct HashBiMap<K, V, KS = DefaultHashBuilder, VS = DefaultHashBuilder>(
    HashBasedBiTable<K, V, (), KS, VS>,
);

fn to_0<'a, T>((t, ()): (&'a T, &())) -> &'a T {
    t
}

fn into_0<T>((t, ()): (T, ())) -> T {
    t
}

impl<K, V, KS, VS> HashBiMap<K, V, KS, VS> {
    pub fn with_hasher(key_hash_builder: KS, value_hash_builder: VS) -> Self {
        Self(HashBasedBiTable::with_hasher(
            key_hash_builder,
            value_hash_builder,
        ))
    }

    pub fn with_capacity_and_hasher(
        capacity: usize,
        key_hash_builder: KS,
        value_hash_builder: VS,
    ) -> Self {
        Self(HashBasedBiTable::with_capacity_and_hasher(
            capacity,
            key_hash_builder,
            value_hash_builder,
        ))
    }
}

impl<K, V, KS, VS> Default for HashBiMap<K, V, KS, VS>
where
    KS: Default,
    VS: Default,
{
    fn default() -> Self {
        Self::with_hasher(Default::default(), Default::default())
    }
}

impl<K, V> HashBiMap<K, V> {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_capacity(capacity: usize) -> Self {
        Self::with_capacity_and_hasher(capacity, Default::default(), Default::default())
    }
}

impl<K, V, KS, VS> Extend<(K, V)> for HashBiMap<K, V, KS, VS>
where
    K: Eq + Hash,
    V: Eq + Hash,
    KS: BuildHasher,
    VS: BuildHasher,
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

impl<K, V, KS, VS, const N: usize> From<[(K, V); N]> for HashBiMap<K, V, KS, VS>
where
    K: Eq + Hash,
    V: Eq + Hash,
    KS: BuildHasher + Default,
    VS: BuildHasher + Default,
{
    fn from(arr: [(K, V); N]) -> Self {
        let mut bimap = Self::with_capacity_and_hasher(N, Default::default(), Default::default());
        bimap.extend(arr);
        bimap
    }
}

impl<K, V, KS, VS> FromIterator<(K, V)> for HashBiMap<K, V, KS, VS>
where
    K: Eq + Hash,
    V: Eq + Hash,
    KS: BuildHasher + Default,
    VS: BuildHasher + Default,
{
    fn from_iter<I>(iter: I) -> Self
    where
        I: IntoIterator<Item = (K, V)>,
    {
        let mut bimap = Self::default();
        bimap.extend(iter);
        bimap
    }
}

impl<K, V, KS, VS> Debug for HashBiMap<K, V, KS, VS>
where
    K: Debug,
    V: Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_map().entries(self.iter()).finish()
    }
}

impl<K, V, KS, VS> PartialEq for HashBiMap<K, V, KS, VS>
where
    K: Eq + Hash,
    V: Eq + Hash,
    KS: BuildHasher,
    VS: BuildHasher,
{
    fn eq(&self, other: &Self) -> bool {
        self.len() == other.len() && self.iter().all(|(k, v)| other.contains(k, v))
    }
}

impl<K, V, KS, VS> Eq for HashBiMap<K, V, KS, VS>
where
    K: Eq + Hash,
    V: Eq + Hash,
    KS: BuildHasher,
    VS: BuildHasher,
{
}

impl<K, V, KS, VS> HashBiMap<K, V, KS, VS> {
    pub fn capacity(&self) -> usize {
        self.0.capacity()
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn len(&self) -> usize {
        self.0.len()
    }

    pub fn keys(&self) -> impl Iterator<Item = &K> {
        self.0.rows()
    }

    pub fn values(&self) -> impl Iterator<Item = &V> {
        self.0.columns()
    }

    pub fn iter(&self) -> impl Iterator<Item = (&K, &V)> {
        self.0.iter().map(|(k, v, _)| (k, v))
    }

    pub fn clear(&mut self) {
        self.0.clear();
    }
}

impl<K, V, KS, VS> HashBiMap<K, V, KS, VS>
where
    K: Eq + Hash,
    V: Eq + Hash,
    KS: BuildHasher,
    VS: BuildHasher,
{
    pub fn contains_key<Q>(&self, key: &Q) -> bool
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.0.contains_row(key)
    }

    pub fn contains_value<Q>(&self, value: &Q) -> bool
    where
        V: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.0.contains_column(value)
    }

    pub fn contains<KQ, VQ>(&self, key: &KQ, value: &VQ) -> bool
    where
        K: Borrow<KQ>,
        KQ: Eq + Hash + ?Sized,
        V: Borrow<VQ>,
        VQ: Eq + Hash + ?Sized,
    {
        self.0.contains(key, value)
    }

    pub fn get<Q>(&self, key: &Q) -> Option<&V>
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.0.get_row(key).map(to_0)
    }

    pub fn inverse_get<Q>(&self, value: &Q) -> Option<&K>
    where
        V: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.0.get_column(value).map(to_0)
    }

    // TODO: Provide an `entry` method equivalent to `HashMap::entry`.

    pub fn insert(&mut self, key: K, value: V) -> (Option<V>, Option<K>) {
        match self.0.insert(key, value, ()) {
            Ok((k, v, ())) => (Some(v), Some(k)),
            Err((v, k)) => (v.map(into_0), k.map(into_0)),
        }
    }

    pub fn remove_key<Q>(&mut self, key: &Q) -> Option<V>
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.0.remove_row(key).map(into_0)
    }

    pub fn remove_value<Q>(&mut self, value: &Q) -> Option<K>
    where
        V: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.0.remove_column(value).map(into_0)
    }

    pub fn remove<KQ, VQ>(&mut self, key: &KQ, value: &VQ) -> bool
    where
        K: Borrow<KQ>,
        KQ: Eq + Hash + ?Sized,
        V: Borrow<VQ>,
        VQ: Eq + Hash + ?Sized,
    {
        self.0.remove(key, value).is_some()
    }
}

#[cfg(test)]
mod test_harness {
    use crate::iter::IteratorExt;

    use super::*;

    impl HashBiMap<char, usize> {
        pub fn assert_map(&self, expect: &[(char, usize)]) {
            assert_eq!(self.is_empty(), expect.is_empty());
            assert_eq!(self.len(), expect.len());

            assert_eq!(
                self.keys().collect_then_sort(),
                expect.iter().map(|(k, _)| k).collect_then_sort(),
            );
            assert_eq!(
                self.values().collect_then_sort(),
                expect.iter().map(|(_, v)| v).collect_then_sort(),
            );
            assert_eq!(
                self.iter().collect_then_sort(),
                expect.iter().map(|(k, v)| (k, v)).collect_then_sort(),
            );

            for (k, v) in expect {
                assert_eq!(self.contains_key(k), true);
                assert_eq!(self.contains_value(v), true);
                assert_eq!(self.contains(k, v), true);
                assert_eq!(self.get(k), Some(v));
                assert_eq!(self.inverse_get(v), Some(k));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new() {
        let map1 = HashBiMap::new();
        map1.assert_map(&[]);
        assert_eq!(map1.capacity(), 0);

        let map2 = HashBiMap::with_capacity(4);
        map2.assert_map(&[]);
        assert_eq!(map2.capacity(), 4);

        assert_eq!(map1, map2);
        assert_ne!(map1.capacity(), map2.capacity());

        HashBiMap::default().assert_map(&[]);

        let expect = [('a', 100)];
        HashBiMap::from(expect).assert_map(&expect);
        let expect = [('a', 100), ('c', 102)];
        HashBiMap::from(expect).assert_map(&expect);
        let expect = [('a', 100), ('c', 102), ('b', 101)];
        HashBiMap::from(expect).assert_map(&expect);
    }

    #[test]
    fn eq() {
        assert_eq!(
            HashBiMap::<char, usize>::from([('a', 100), ('b', 101)]),
            HashBiMap::from([('b', 101), ('a', 100)]),
        );

        assert_ne!(
            HashBiMap::<char, usize>::from([('a', 100)]),
            HashBiMap::from([('b', 101), ('a', 100)]),
        );
        assert_ne!(
            HashBiMap::<char, usize>::from([('a', 101), ('b', 100)]),
            HashBiMap::from([('b', 101), ('a', 100)]),
        );
    }

    #[test]
    fn clear() {
        let mut map = HashBiMap::from([('a', 100), ('b', 101)]);
        map.assert_map(&[('a', 100), ('b', 101)]);

        map.clear();
        map.assert_map(&[]);
    }

    #[test]
    fn contains_and_get() {
        let map = HashBiMap::from([('a', 100), ('b', 101)]);
        map.assert_map(&[('a', 100), ('b', 101)]);

        assert_eq!(map.contains_key(&'a'), true);
        assert_eq!(map.contains_key(&'b'), true);
        assert_eq!(map.contains_key(&'c'), false);

        assert_eq!(map.contains_value(&100), true);
        assert_eq!(map.contains_value(&101), true);
        assert_eq!(map.contains_value(&102), false);

        assert_eq!(map.contains(&'a', &100), true);
        assert_eq!(map.contains(&'b', &101), true);
        assert_eq!(map.contains(&'a', &101), false);
        assert_eq!(map.contains(&'b', &100), false);

        assert_eq!(map.get(&'a'), Some(&100));
        assert_eq!(map.get(&'b'), Some(&101));
        assert_eq!(map.get(&'c'), None);

        assert_eq!(map.inverse_get(&100), Some(&'a'));
        assert_eq!(map.inverse_get(&101), Some(&'b'));
        assert_eq!(map.inverse_get(&102), None);
    }

    #[test]
    fn insert() {
        let mut map = HashBiMap::new();
        map.assert_map(&[]);

        assert_eq!(map.insert('a', 100), (None, None));
        map.assert_map(&[('a', 100)]);
        assert_eq!(map.insert('a', 100), (Some(100), Some('a')));
        map.assert_map(&[('a', 100)]);

        assert_eq!(map.insert('a', 101), (Some(100), None));
        map.assert_map(&[('a', 101)]);

        assert_eq!(map.insert('b', 101), (None, Some('a')));
        map.assert_map(&[('b', 101)]);

        let mut map = HashBiMap::from([('a', 100), ('b', 101)]);
        map.assert_map(&[('a', 100), ('b', 101)]);
        assert_eq!(map.insert('a', 101), (Some(100), Some('b')));
        map.assert_map(&[('a', 101)]);
    }

    #[test]
    fn remove() {
        let mut map = HashBiMap::from([('a', 100), ('b', 101)]);
        map.assert_map(&[('a', 100), ('b', 101)]);
        assert_eq!(map.remove_key(&'a'), Some(100));
        map.assert_map(&[('b', 101)]);
        assert_eq!(map.remove_key(&'a'), None);
        map.assert_map(&[('b', 101)]);

        let mut map = HashBiMap::from([('a', 100), ('b', 101)]);
        map.assert_map(&[('a', 100), ('b', 101)]);
        assert_eq!(map.remove_value(&101), Some('b'));
        map.assert_map(&[('a', 100)]);
        assert_eq!(map.remove_value(&101), None);
        map.assert_map(&[('a', 100)]);

        let mut map = HashBiMap::from([('a', 100), ('b', 101)]);
        map.assert_map(&[('a', 100), ('b', 101)]);

        assert_eq!(map.remove(&'a', &101), false);
        map.assert_map(&[('a', 100), ('b', 101)]);

        assert_eq!(map.remove(&'a', &100), true);
        map.assert_map(&[('b', 101)]);
        assert_eq!(map.remove(&'a', &100), false);
        map.assert_map(&[('b', 101)]);
    }
}
