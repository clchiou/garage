//! Set in which elements can be accessed by cursors.

use std::borrow::Borrow;
use std::fmt::{self, Debug};
use std::hash::{BuildHasher, Hash};
use std::ops::Index;

use super::{
    DefaultHashBuilder,
    index_map::{Entry, HashIndexMap, IdentityAsHash},
    vec_list::VecList,
};

pub use super::vec_list::Cursor;

#[derive(Clone)]
pub struct HashCursorSet<T, S = DefaultHashBuilder> {
    map: HashIndexMap<Cursor, IdentityAsHash, T, T, S>,
    elements: VecList<T>,
}

impl<T, S> HashCursorSet<T, S> {
    pub fn with_hasher(hash_builder: S) -> Self {
        Self {
            map: HashIndexMap::with_hasher(hash_builder),
            elements: VecList::new(),
        }
    }

    pub fn with_capacity_and_hasher(capacity: usize, hash_builder: S) -> Self {
        Self {
            map: HashIndexMap::with_capacity_and_hasher(capacity, hash_builder),
            elements: VecList::with_capacity(capacity),
        }
    }
}

impl<T, S> Default for HashCursorSet<T, S>
where
    S: Default,
{
    fn default() -> Self {
        Self::with_hasher(Default::default())
    }
}

impl<T> HashCursorSet<T> {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_capacity(capacity: usize) -> Self {
        Self::with_capacity_and_hasher(capacity, Default::default())
    }
}

impl<T, S> Extend<T> for HashCursorSet<T, S>
where
    T: Eq + Hash,
    S: BuildHasher,
{
    fn extend<I>(&mut self, iter: I)
    where
        I: IntoIterator<Item = T>,
    {
        for element in iter {
            self.insert(element);
        }
    }
}

impl<T, S, const N: usize> From<[T; N]> for HashCursorSet<T, S>
where
    T: Eq + Hash,
    S: BuildHasher + Default,
{
    fn from(arr: [T; N]) -> Self {
        let mut bimap = Self::with_capacity_and_hasher(N, Default::default());
        bimap.extend(arr);
        bimap
    }
}

impl<T, S> FromIterator<T> for HashCursorSet<T, S>
where
    T: Eq + Hash,
    S: BuildHasher + Default,
{
    fn from_iter<I>(iter: I) -> Self
    where
        I: IntoIterator<Item = T>,
    {
        let mut bimap = Self::default();
        bimap.extend(iter);
        bimap
    }
}

impl<T, S> Debug for HashCursorSet<T, S>
where
    T: Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_set().entries(self.iter()).finish()
    }
}

impl<T, S> PartialEq for HashCursorSet<T, S>
where
    T: Eq + Hash,
    S: BuildHasher,
{
    fn eq(&self, other: &Self) -> bool {
        self.len() == other.len() && self.iter().all(|e| other.contains(e))
    }
}

impl<T, S> Eq for HashCursorSet<T, S>
where
    T: Eq + Hash,
    S: BuildHasher,
{
}

impl<T, S> HashCursorSet<T, S> {
    pub fn capacity(&self) -> usize {
        self.elements.capacity()
    }

    pub fn is_empty(&self) -> bool {
        self.elements.is_empty()
    }

    pub fn len(&self) -> usize {
        self.elements.len()
    }

    pub fn iter(&self) -> impl Iterator<Item = &T> {
        self.elements.iter()
    }

    pub fn cursors(&self) -> impl Iterator<Item = Cursor> + '_ {
        self.map.iter()
    }

    pub fn get(&self, cursor: Cursor) -> Option<&T> {
        self.elements.get(cursor)
    }

    pub fn clear(&mut self) {
        self.map.clear();
        self.elements.clear();
    }
}

impl<T, S> Index<Cursor> for HashCursorSet<T, S> {
    type Output = T;

    fn index(&self, cursor: Cursor) -> &Self::Output {
        &self.elements[cursor]
    }
}

impl<T, S> HashCursorSet<T, S>
where
    T: Eq + Hash,
    S: BuildHasher,
{
    pub fn contains<Q>(&self, element: &Q) -> bool
    where
        T: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.find(element).is_some()
    }

    pub fn find<Q>(&self, element: &Q) -> Option<Cursor>
    where
        T: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.map.get(&self.elements, element)
    }

    pub fn insert(&mut self, element: T) -> (bool, Cursor) {
        match self.map.entry(&self.elements, &element) {
            Entry::Occupied(entry) => (false, *entry.get()),
            Entry::Vacant(entry) => (true, *entry.insert(self.elements.push_back(element)).get()),
        }
    }

    pub fn remove<Q>(&mut self, element: &Q) -> Option<Cursor>
    where
        T: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.map.remove(&self.elements, element).inspect(|&p| {
            self.elements.remove(p);
        })
    }

    pub fn remove_cursor(&mut self, cursor: Cursor) -> T {
        self.map.remove(&self.elements, &self.elements[cursor]);
        self.elements.remove(cursor)
    }
}

#[cfg(test)]
mod test_harness {
    use crate::iter::IteratorExt;

    use super::*;

    impl HashCursorSet<usize> {
        pub fn assert_set(&self, expect: &[usize]) {
            assert_eq!(self.is_empty(), expect.is_empty());
            assert_eq!(self.len(), expect.len());

            assert_eq!(
                self.iter().collect_then_sort(),
                expect.iter().collect_then_sort(),
            );

            for element in expect {
                assert_eq!(self.contains(element), true);
                let p = self.find(element).unwrap();
                assert_eq!(self.get(p), Some(element));
                assert_eq!(&self[p], element);
            }

            self.assert_cursors();
        }

        pub fn assert_cursors(&self) {
            let mut cursors = Vec::new();
            let mut p = self.elements.cursor_front();
            while let Some(cursor) = p {
                cursors.push(usize::from(cursor));
                p = self.elements.next(cursor);
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
        let set1 = HashCursorSet::new();
        set1.assert_set(&[]);
        assert_eq!(set1.capacity(), 0);

        let set2 = HashCursorSet::with_capacity(4);
        set2.assert_set(&[]);
        assert_eq!(set2.capacity(), 4);

        assert_eq!(set1, set2);
        assert_ne!(set1.capacity(), set2.capacity());

        HashCursorSet::default().assert_set(&[]);

        let expect = [100];
        HashCursorSet::from(expect).assert_set(&expect);
        let expect = [100, 102];
        HashCursorSet::from(expect).assert_set(&expect);
        let expect = [100, 102, 101];
        HashCursorSet::from(expect).assert_set(&expect);
    }

    #[test]
    fn eq() {
        assert_eq!(
            HashCursorSet::<usize>::from([100, 101]),
            HashCursorSet::from([101, 100]),
        );

        assert_ne!(
            HashCursorSet::<usize>::from([100]),
            HashCursorSet::from([101, 100]),
        );
        assert_ne!(
            HashCursorSet::<usize>::from([100, 101]),
            HashCursorSet::from([100, 102]),
        );
    }

    #[test]
    fn clear() {
        let mut set = HashCursorSet::from([100, 101]);
        set.assert_set(&[100, 101]);

        set.clear();
        set.assert_set(&[]);
    }

    #[test]
    fn find() {
        let set = HashCursorSet::<usize>::from([100]);
        let p = set.elements.cursor_front().unwrap();

        assert_eq!(set.contains(&100), true);
        assert_eq!(set.contains(&101), false);

        assert_eq!(set.find(&100), Some(p));
        assert_eq!(set.find(&101), None);
    }

    #[test]
    fn insert() {
        let mut set = HashCursorSet::new();
        set.assert_set(&[]);

        let (x, p) = set.insert(100);
        assert_eq!(x, true);
        assert_eq!(p, set.elements.cursor_back().unwrap());
        set.assert_set(&[100]);

        assert_eq!(set.insert(100), (false, p));
        set.assert_set(&[100]);

        let (x, p) = set.insert(101);
        assert_eq!(x, true);
        assert_eq!(p, set.elements.cursor_back().unwrap());
        set.assert_set(&[100, 101]);
    }

    #[test]
    fn remove() {
        let mut set = HashCursorSet::from([100, 101]);
        set.assert_set(&[100, 101]);

        let p = set.elements.cursor_front().unwrap();
        assert_eq!(set[p], 100);
        let q = set.elements.cursor_back().unwrap();
        assert_eq!(set[q], 101);

        assert_eq!(set.remove(&100), Some(p));
        set.assert_set(&[101]);

        assert_eq!(set.remove(&100), None);
        set.assert_set(&[101]);

        assert_eq!(set.remove(&101), Some(q));
        set.assert_set(&[]);
    }

    #[test]
    fn remove_cursor() {
        let mut set = HashCursorSet::from([100, 101, 102]);
        set.assert_set(&[100, 101, 102]);

        let p = set.elements.cursor_front().unwrap();
        assert_eq!(set[p], 100);

        assert_eq!(set.remove_cursor(p), 100);
        set.assert_set(&[101, 102]);
    }
}
