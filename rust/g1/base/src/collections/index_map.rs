//! Index Map
//!
//! For an indexable collection type, such as `Vec`, an index map maps values back to their index.
//! It should be noted that maintaining synchronization between a index map and its collection is
//! your responsibility, and now, collection values must be unique.

use std::borrow::Borrow;
use std::hash::{BuildHasher, Hash};
use std::marker::PhantomData;
use std::mem;
use std::ops::Index;

use hashbrown::HashTable;

use super::DefaultHashBuilder;

// Reexport these from hashbrown.
pub use hashbrown::hash_table::{Entry, OccupiedEntry, VacantEntry};

#[derive(Clone, Debug)]
pub struct HashIndexMap<I, F, T, H, S = DefaultHashBuilder> {
    indexes: HashTable<I>,
    hash_builder: S,
    _phantom: PhantomData<(F, T, H)>,
}

pub trait AsHash<T, H>
where
    H: Eq + Hash,
{
    fn as_hash(value: &T) -> &H;
}

#[derive(Clone, Debug)]
pub struct IdentityAsHash;

#[derive(Clone, Debug)]
pub struct KeyAsHash;

#[derive(Clone, Debug)]
pub struct ValueAsHash;

impl<I, F, T, H, S> HashIndexMap<I, F, T, H, S> {
    pub fn with_hasher(hash_builder: S) -> Self {
        Self {
            indexes: HashTable::new(),
            hash_builder,
            _phantom: PhantomData,
        }
    }

    pub fn with_capacity_and_hasher(capacity: usize, hash_builder: S) -> Self {
        Self {
            indexes: HashTable::with_capacity(capacity),
            hash_builder,
            _phantom: PhantomData,
        }
    }
}

impl<I, F, T, H, S> Default for HashIndexMap<I, F, T, H, S>
where
    S: Default,
{
    fn default() -> Self {
        Self::with_hasher(Default::default())
    }
}

impl<I, F, T, H> HashIndexMap<I, F, T, H> {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_capacity(capacity: usize) -> Self {
        Self::with_capacity_and_hasher(capacity, Default::default())
    }
}

impl<I, F, T, H, S> HashIndexMap<I, F, T, H, S> {
    pub fn capacity(&self) -> usize {
        self.indexes.capacity()
    }

    pub fn is_empty(&self) -> bool {
        self.indexes.is_empty()
    }

    pub fn len(&self) -> usize {
        self.indexes.len()
    }

    pub fn clear(&mut self) {
        self.indexes.clear();
    }
}

impl<I, F, T, H, S> HashIndexMap<I, F, T, H, S>
where
    I: Copy, // It seems reasonable to require `Copy` for container index type.
{
    pub fn iter(&self) -> impl Iterator<Item = I> + '_ {
        self.indexes.iter().copied()
    }
}

impl<I, F, T, H, S> HashIndexMap<I, F, T, H, S>
where
    I: Copy, // It seems reasonable to require `Copy` for container index type.
    F: AsHash<T, H>,
    H: Eq + Hash,
    S: BuildHasher,
{
    pub fn get<C, Q>(&self, collection: &C, value: &Q) -> Option<I>
    where
        C: Index<I, Output = T> + ?Sized,
        H: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        let hash = self.hash_builder.hash_one(value);
        let eq = Self::make_eq(collection, value);
        self.indexes.find(hash, eq).copied()
    }

    pub fn entry<C, Q>(&mut self, collection: &C, value: &Q) -> Entry<'_, I>
    where
        C: Index<I, Output = T> + ?Sized,
        H: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        let hash = self.hash_builder.hash_one(value);
        let eq = Self::make_eq(collection, value);
        let hasher = Self::make_hasher(&self.hash_builder, collection);
        self.indexes.entry(hash, eq, hasher)
    }

    pub fn insert<C, Q>(&mut self, collection: &C, value: &Q, mut index: I) -> Option<I>
    where
        C: Index<I, Output = T> + ?Sized,
        H: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        match self.entry(collection, value) {
            Entry::Occupied(mut entry) => {
                mem::swap(entry.get_mut(), &mut index);
                Some(index)
            }
            Entry::Vacant(entry) => {
                entry.insert(index);
                None
            }
        }
    }

    pub fn find_entry<C, Q>(&mut self, collection: &C, value: &Q) -> Option<OccupiedEntry<'_, I>>
    where
        C: Index<I, Output = T> + ?Sized,
        H: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        let hash = self.hash_builder.hash_one(value);
        let eq = Self::make_eq(collection, value);
        self.indexes.find_entry(hash, eq).ok()
    }

    pub fn remove<C, Q>(&mut self, collection: &C, value: &Q) -> Option<I>
    where
        C: Index<I, Output = T> + ?Sized,
        H: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.find_entry(collection, value)
            .map(|entry| entry.remove().0)
    }

    fn make_hasher<'a, C>(hash_builder: &'a S, collection: &'a C) -> impl Fn(&I) -> u64 + 'a
    where
        C: Index<I, Output = T> + ?Sized,
    {
        |&i| hash_builder.hash_one(F::as_hash(&collection[i]))
    }

    fn make_eq<'a, C, Q>(collection: &'a C, value: &'a Q) -> impl Fn(&I) -> bool + 'a
    where
        C: Index<I, Output = T> + ?Sized,
        H: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        move |&i| F::as_hash(&collection[i]).borrow() == value
    }
}

impl<T> AsHash<T, T> for IdentityAsHash
where
    T: Eq + Hash,
{
    fn as_hash(x: &T) -> &T {
        x
    }
}

impl<K, V> AsHash<(K, V), K> for KeyAsHash
where
    K: Eq + Hash,
{
    fn as_hash((key, _): &(K, V)) -> &K {
        key
    }
}

impl<K, V> AsHash<(K, V), V> for ValueAsHash
where
    V: Eq + Hash,
{
    fn as_hash((_, value): &(K, V)) -> &V {
        value
    }
}

#[cfg(test)]
mod test_harness {
    use crate::iter::IteratorExt;

    use super::*;

    impl<T> From<&[T]> for HashIndexMap<usize, IdentityAsHash, T, T>
    where
        T: Eq + Hash,
    {
        fn from(slice: &[T]) -> Self {
            let mut map = Self::with_capacity(slice.len());
            for (i, value) in slice.iter().enumerate() {
                map.insert(slice, value, i);
            }
            map
        }
    }

    impl<T> HashIndexMap<usize, IdentityAsHash, T, T>
    where
        T: Eq + Hash,
    {
        pub fn assert_map(&self, collection: &[T], expect: &[usize]) {
            assert_eq!(self.is_empty(), expect.is_empty());
            assert_eq!(self.len(), expect.len());
            self.assert_indexes(expect);
            for (i, value) in collection.iter().enumerate() {
                assert_eq!(
                    self.get(collection, value),
                    expect.contains(&i).then_some(i),
                );
            }
        }

        pub fn assert_indexes(&self, expect: &[usize]) {
            assert_eq!(self.iter().collect_then_sort(), expect);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clear() {
        let collection = &['a', 'b', 'c'];
        let mut indexes = HashIndexMap::from(collection.as_slice());
        indexes.assert_map(collection, &[0, 1, 2]);

        indexes.clear();
        indexes.assert_map(collection, &[]);
    }

    #[test]
    fn insert() {
        let collection = &['a', 'b', 'c'];
        let mut indexes = HashIndexMap::new();
        indexes.assert_map(collection, &[]);

        assert_eq!(indexes.insert(collection, &'b', 1), None);
        indexes.assert_map(collection, &[1]);
        assert_eq!(indexes.insert(collection, &'b', 1), Some(1));
        indexes.assert_map(collection, &[1]);

        assert_eq!(indexes.insert(collection, &'c', 2), None);
        indexes.assert_map(collection, &[1, 2]);

        assert_eq!(indexes.insert(collection, &'a', 0), None);
        indexes.assert_map(collection, &[0, 1, 2]);
    }

    #[test]
    fn remove() {
        let collection = &['a', 'b', 'c'];
        let mut indexes = HashIndexMap::from(collection.as_slice());
        indexes.assert_map(collection, &[0, 1, 2]);

        assert_eq!(indexes.remove(collection, &'d'), None);
        indexes.assert_map(collection, &[0, 1, 2]);

        assert_eq!(indexes.remove(collection, &'b'), Some(1));
        indexes.assert_map(collection, &[0, 2]);
        assert_eq!(indexes.remove(collection, &'b'), None);
        indexes.assert_map(collection, &[0, 2]);

        assert_eq!(indexes.remove(collection, &'a'), Some(0));
        indexes.assert_map(collection, &[2]);

        assert_eq!(indexes.remove(collection, &'c'), Some(2));
        indexes.assert_map(collection, &[]);
    }

    // TODO: In the following test cases, we demonstrate how to maintain synchronization for some
    // common operations.  However, the code appears to be error-prone.  How can we improve the
    // `HashIndexMap` interface to make it easier to use correctly?

    #[test]
    fn collection_assign() {
        let mut indexes = HashIndexMap::from(['a', 'b', 'c'].as_slice());
        indexes.assert_map(&['a', 'b', 'c'], &[0, 1, 2]);

        assert_eq!(indexes.remove(&['a', 'b', 'c'], &'b'), Some(1));
        indexes.assert_indexes(&[0, 2]);

        assert_eq!(indexes.insert(&['a', 'd', 'c'], &'d', 1), None);
        indexes.assert_map(&['a', 'd', 'c'], &[0, 1, 2]);
    }

    #[test]
    fn collection_swap() {
        let mut indexes = HashIndexMap::from(['a', 'b', 'c'].as_slice());
        indexes.assert_map(&['a', 'b', 'c'], &[0, 1, 2]);

        assert_eq!(indexes.insert(&['a', 'b', 'c'], &'b', 2), Some(1));
        indexes.assert_indexes(&[0, 2, 2]);

        assert_eq!(indexes.insert(&['a', 'b', 'c'], &'c', 1), Some(2));
        indexes.assert_map(&['a', 'c', 'b'], &[0, 1, 2]);
    }

    #[test]
    fn collection_insert() {
        let mut indexes = HashIndexMap::from(['a', 'b'].as_slice());
        indexes.assert_map(&['a', 'b'], &[0, 1]);

        assert_eq!(indexes.insert(&['a', 'b'], &'b', 2), Some(1));
        indexes.assert_indexes(&[0, 2]);

        assert_eq!(indexes.insert(&['a', 'c', 'b'], &'c', 1), None);
        indexes.assert_map(&['a', 'c', 'b'], &[0, 1, 2]);
    }

    #[test]
    fn collection_remove() {
        let mut indexes = HashIndexMap::from(['a', 'b', 'c'].as_slice());
        indexes.assert_map(&['a', 'b', 'c'], &[0, 1, 2]);

        assert_eq!(indexes.remove(&['a', 'b', 'c'], &'b'), Some(1));
        indexes.assert_indexes(&[0, 2]);

        assert_eq!(indexes.insert(&['a', 'b', 'c'], &'c', 1), Some(2));
        indexes.assert_map(&['a', 'c'], &[0, 1]);
    }
}
