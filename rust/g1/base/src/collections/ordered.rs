//! Collection modeled after `OrderedDict` in Python.

use std::borrow::Borrow;
use std::cell::RefCell;
use std::fmt::{self, Debug};
use std::hash::{BuildHasher, Hash};
use std::iter::FusedIterator;
use std::mem;
use std::rc::Rc;

use super::{
    DefaultHashBuilder,
    index_map::{self, HashIndexMap, KeyAsHash},
    vec_list::{Cursor, VecList},
};

#[derive(Clone)]
pub struct HashOrderedMap<K, V, S = DefaultHashBuilder> {
    map: HashIndexMap<Cursor, KeyAsHash, (K, V), K, S>,
    entries: VecList<(K, V)>,
}

#[derive(Debug)]
pub enum Entry<'a, K, V> {
    Occupied(OccupiedEntry<'a, K, V>),
    Vacant(VacantEntry<'a, K, V>),
}

#[derive(Debug)]
pub struct OccupiedEntry<'a, K, V> {
    entries: &'a mut VecList<(K, V)>,
    cursor_entry: index_map::OccupiedEntry<'a, Cursor>,
}

#[derive(Debug)]
pub struct VacantEntry<'a, K, V> {
    entries: &'a mut VecList<(K, V)>,
    key: K,
    cursor_entry: index_map::VacantEntry<'a, Cursor>,
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

pub type ExtractIf<'a, K, V, S, F>
    = impl FusedIterator<Item = (K, V)>
where
    K: 'a,
    V: 'a,
    F: FnMut(&K, &mut V) -> bool;

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
                .all(|(key, value)| other.get(key) == Some(value))
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

    #[define_opaque(ExtractIf)]
    pub fn extract_if<F>(&mut self, mut f: F) -> ExtractIf<'_, K, V, S, F>
    where
        F: FnMut(&K, &mut V) -> bool,
    {
        let entries = Rc::new(RefCell::new(&mut self.entries));
        let predicate = {
            let entries = entries.clone();
            move |p: &mut Cursor| {
                let mut entries = entries.borrow_mut();
                let (k, v) = &mut entries[*p];
                f(k, v)
            }
        };
        self.map
            .extract_if(predicate)
            .map(move |p| entries.borrow_mut().remove(p))
    }

    pub fn retain<F>(&mut self, mut f: F)
    where
        F: FnMut(&K, &mut V) -> bool,
    {
        self.map.retain(|p| {
            let (k, v) = &mut self.entries[*p];
            let retain = f(k, v);
            if !retain {
                self.entries.remove(*p);
            }
            retain
        })
    }

    pub fn clear(&mut self) {
        self.map.clear();
        self.entries.clear();
    }

    pub fn front(&self) -> Option<(&K, &V)> {
        self.entries.front().map(|(k, v)| (k, v))
    }

    pub fn front_mut(&mut self) -> Option<(&K, &mut V)> {
        self.entries.front_mut().map(|(k, v)| (&*k, v))
    }

    pub fn back(&self) -> Option<(&K, &V)> {
        self.entries.back().map(|(k, v)| (k, v))
    }

    pub fn back_mut(&mut self) -> Option<(&K, &mut V)> {
        self.entries.back_mut().map(|(k, v)| (&*k, v))
    }
}

impl<K, V, S> HashOrderedMap<K, V, S> {
    #[define_opaque(Keys)]
    pub fn keys(&self) -> Keys<'_, K, V, S> {
        self.entries.iter().map(|(k, _)| k)
    }

    #[define_opaque(Values)]
    pub fn values(&self) -> Values<'_, K, V, S> {
        self.entries.iter().map(|(_, v)| v)
    }

    #[define_opaque(ValuesMut)]
    pub fn values_mut(&mut self) -> ValuesMut<'_, K, V, S> {
        self.entries.iter_mut().map(|(_, v)| v)
    }

    #[define_opaque(Iter)]
    pub fn iter(&self) -> Iter<'_, K, V, S> {
        self.entries.iter().map(|(k, v)| (k, v))
    }

    #[define_opaque(IterMut)]
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

    pub fn entry(&mut self, key: K) -> Entry<'_, K, V> {
        match self.map.entry(&self.entries, &key) {
            index_map::Entry::Occupied(cursor_entry) => Entry::Occupied(OccupiedEntry {
                entries: &mut self.entries,
                cursor_entry,
            }),
            index_map::Entry::Vacant(cursor_entry) => Entry::Vacant(VacantEntry {
                entries: &mut self.entries,
                key,
                cursor_entry,
            }),
        }
    }

    pub fn find_entry<Q>(&mut self, key: &Q) -> Option<OccupiedEntry<'_, K, V>>
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.map
            .find_entry(&self.entries, key)
            .map(|cursor_entry| OccupiedEntry {
                entries: &mut self.entries,
                cursor_entry,
            })
    }

    pub fn front_entry(&mut self) -> Option<OccupiedEntry<'_, K, V>> {
        self.occupied_entry(VecList::front)
    }

    pub fn back_entry(&mut self) -> Option<OccupiedEntry<'_, K, V>> {
        self.occupied_entry(VecList::back)
    }

    #[allow(clippy::type_complexity)]
    fn occupied_entry(
        &mut self,
        f: fn(&VecList<(K, V)>) -> Option<&(K, V)>,
    ) -> Option<OccupiedEntry<'_, K, V>> {
        let cursor_entry = self
            .map
            .find_entry(&self.entries, &f(&self.entries)?.0)
            .expect("HashOrderedMap index_map invariant");
        Some(OccupiedEntry {
            entries: &mut self.entries,
            cursor_entry,
        })
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

    pub fn insert(&mut self, key: K, value: V) -> Option<V> {
        match self.entry(key) {
            Entry::Occupied(mut entry) => Some(entry.insert(value)),
            Entry::Vacant(entry) => {
                entry.insert(value);
                None
            }
        }
    }

    /// Similar to `insert`, but moves the entry (existing or otherwise) to the back.
    pub fn insert_back(&mut self, key: K, value: V) -> Option<V> {
        match self.entry(key) {
            Entry::Occupied(entry) => Some(entry.move_back().insert(value)),
            Entry::Vacant(entry) => {
                entry.insert(value);
                None
            }
        }
    }

    pub fn remove<Q>(&mut self, key: &Q) -> Option<V>
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        Some(self.find_entry(key)?.remove())
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
        Some(self.front_entry()?.remove_entry())
    }

    pub fn pop_back(&mut self) -> Option<(K, V)> {
        Some(self.back_entry()?.remove_entry())
    }
}

impl<'a, K, V> Entry<'a, K, V> {
    pub fn key(&self) -> &K {
        match self {
            Self::Occupied(entry) => entry.key(),
            Self::Vacant(entry) => entry.key(),
        }
    }

    pub fn and_modify<F>(mut self, f: F) -> Self
    where
        F: FnOnce(&mut V),
    {
        match self {
            Self::Occupied(ref mut entry) => {
                f(entry.get_mut());
                self
            }
            Self::Vacant(_) => self,
        }
    }

    // NOTE: Like `and_modify`, this is a no-op when the entry is vacant.
    pub fn and_move_front(self) -> Self {
        match self {
            Self::Occupied(entry) => Self::Occupied(entry.move_front()),
            Self::Vacant(_) => self,
        }
    }

    // NOTE: Like `and_modify`, this is a no-op when the entry is vacant.
    pub fn and_move_back(self) -> Self {
        match self {
            Self::Occupied(entry) => Self::Occupied(entry.move_back()),
            Self::Vacant(_) => self,
        }
    }

    pub fn or_default(self) -> &'a mut V
    where
        V: Default,
    {
        match self {
            Self::Occupied(entry) => entry.into_mut(),
            Self::Vacant(entry) => entry.insert(Default::default()),
        }
    }

    pub fn or_insert(self, default: V) -> &'a mut V {
        match self {
            Self::Occupied(entry) => entry.into_mut(),
            Self::Vacant(entry) => entry.insert(default),
        }
    }

    pub fn or_insert_with<F>(self, default: F) -> &'a mut V
    where
        F: FnOnce() -> V,
    {
        match self {
            Self::Occupied(entry) => entry.into_mut(),
            Self::Vacant(entry) => entry.insert(default()),
        }
    }

    pub fn or_insert_with_key<F>(self, default: F) -> &'a mut V
    where
        F: FnOnce(&K) -> V,
    {
        match self {
            Self::Occupied(entry) => entry.into_mut(),
            Self::Vacant(entry) => {
                let value = default(entry.key());
                entry.insert(value)
            }
        }
    }

    pub fn insert_entry(self, value: V) -> OccupiedEntry<'a, K, V> {
        match self {
            Self::Occupied(mut entry) => {
                entry.insert(value);
                entry
            }
            Self::Vacant(entry) => entry.insert_entry(value),
        }
    }
}

impl<'a, K, V> OccupiedEntry<'a, K, V> {
    pub fn key(&self) -> &K {
        &self.entries[*self.cursor_entry.get()].0
    }

    pub fn get(&self) -> &V {
        &self.entries[*self.cursor_entry.get()].1
    }

    pub fn get_mut(&mut self) -> &mut V {
        &mut self.entries[*self.cursor_entry.get()].1
    }

    pub fn move_front(self) -> Self {
        self.entries.move_front(*self.cursor_entry.get());
        self
    }

    pub fn move_back(self) -> Self {
        self.entries.move_back(*self.cursor_entry.get());
        self
    }

    pub fn into_mut(self) -> &'a mut V {
        &mut self.entries[*self.cursor_entry.get()].1
    }

    pub fn insert(&mut self, value: V) -> V {
        mem::replace(&mut self.entries[*self.cursor_entry.get()].1, value)
    }

    pub fn remove(self) -> V {
        self.remove_entry().1
    }

    pub fn remove_entry(self) -> (K, V) {
        self.entries.remove(self.cursor_entry.remove().0)
    }
}

impl<'a, K, V> VacantEntry<'a, K, V> {
    pub fn key(&self) -> &K {
        &self.key
    }

    pub fn into_key(self) -> K {
        self.key
    }

    pub fn insert(self, value: V) -> &'a mut V {
        let p = *self
            .cursor_entry
            .insert(self.entries.push_back((self.key, value)))
            .get();
        &mut self.entries[p].1
    }

    pub fn insert_entry(self, value: V) -> OccupiedEntry<'a, K, V> {
        let cursor_entry = self
            .cursor_entry
            .insert(self.entries.push_back((self.key, value)));
        OccupiedEntry {
            entries: self.entries,
            cursor_entry,
        }
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
    use std::assert_matches::assert_matches;

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
    fn extract_if() {
        let mut map = HashOrderedMap::from([('a', 100), ('b', 101), ('c', 102)]);
        map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);

        assert_eq!(
            map.extract_if(|k, v| match k {
                'a' => true,
                'b' => false,
                'c' => {
                    *v += 1000;
                    false
                }
                _ => panic!(),
            })
            .collect::<Vec<_>>(),
            &[('a', 100)]
        );
        map.assert_map(&[('b', 101), ('c', 1102)]);
    }

    #[test]
    fn retain() {
        let mut map = HashOrderedMap::from([('a', 100), ('b', 101), ('c', 102)]);
        map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);

        map.retain(|k, v| match k {
            'a' => false,
            'b' => true,
            'c' => {
                *v += 1000;
                true
            }
            _ => panic!(),
        });
        map.assert_map(&[('b', 101), ('c', 1102)]);
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
    fn entry_new() {
        let mut map = HashOrderedMap::new();
        map.assert_map(&[]);
        assert_matches!(map.entry('a'), Entry::Vacant(_));
        assert_matches!(map.find_entry(&'a'), None);
        assert_matches!(map.front_entry(), None);
        assert_matches!(map.back_entry(), None);
        map.assert_map(&[]);

        let mut map = HashOrderedMap::from([('a', 100), ('b', 101)]);
        map.assert_map(&[('a', 100), ('b', 101)]);
        assert_matches!(map.entry('a'), Entry::Occupied(entry) if entry.key() == &'a');
        assert_matches!(map.entry('c'), Entry::Vacant(entry) if entry.key() == &'c');
        assert_matches!(map.find_entry(&'a'), Some(entry) if entry.key() == &'a');
        assert_matches!(map.find_entry(&'c'), None);
        assert_matches!(map.front_entry(), Some(entry) if entry.key() == &'a');
        assert_matches!(map.back_entry(), Some(entry) if entry.key() == &'b');
        map.assert_map(&[('a', 100), ('b', 101)]);
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
    fn front_and_back() {
        let mut map = HashOrderedMap::from([]);
        map.assert_map(&[]);
        assert_eq!(map.front(), None);
        assert_eq!(map.front_mut(), None);
        assert_eq!(map.back(), None);
        assert_eq!(map.back_mut(), None);
        map.assert_map(&[]);

        let mut map = HashOrderedMap::from([('a', 100)]);
        map.assert_map(&[('a', 100)]);
        assert_eq!(map.front(), Some((&'a', &100)));
        assert_eq!(map.front_mut(), Some((&'a', &mut 100)));
        assert_eq!(map.back(), Some((&'a', &100)));
        assert_eq!(map.back_mut(), Some((&'a', &mut 100)));
        map.assert_map(&[('a', 100)]);

        let mut map = HashOrderedMap::from([('a', 100), ('b', 101), ('c', 102)]);
        map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);
        assert_eq!(map.front(), Some((&'a', &100)));
        assert_eq!(map.front_mut(), Some((&'a', &mut 100)));
        assert_eq!(map.back(), Some((&'c', &102)));
        assert_eq!(map.back_mut(), Some((&'c', &mut 102)));
        map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);
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

    #[test]
    fn entry_key() {
        let mut map = HashOrderedMap::from([('a', 100)]);
        map.assert_map(&[('a', 100)]);
        assert_eq!(map.entry('a').key(), &'a');
        assert_eq!(map.entry('b').key(), &'b');
        map.assert_map(&[('a', 100)]);
    }

    #[test]
    fn entry_and_func() {
        {
            let mut map = HashOrderedMap::from([('a', 100), ('b', 101)]);
            map.assert_map(&[('a', 100), ('b', 101)]);
            map.entry('a').and_modify(|x| *x += 1000);
            map.assert_map(&[('a', 1100), ('b', 101)]);

            let mut map = HashOrderedMap::from([('a', 100), ('b', 101)]);
            map.assert_map(&[('a', 100), ('b', 101)]);
            map.entry('c').and_modify(|x| *x += 1000);
            map.assert_map(&[('a', 100), ('b', 101)]);
        }

        {
            let mut map = HashOrderedMap::from([('a', 100), ('b', 101), ('c', 102)]);
            map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);
            map.entry('b').and_move_front();
            map.assert_map(&[('b', 101), ('a', 100), ('c', 102)]);

            let mut map = HashOrderedMap::from([('a', 100), ('b', 101), ('c', 102)]);
            map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);
            map.entry('d').and_move_front();
            map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);
        }

        {
            let mut map = HashOrderedMap::from([('a', 100), ('b', 101), ('c', 102)]);
            map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);
            map.entry('b').and_move_back();
            map.assert_map(&[('a', 100), ('c', 102), ('b', 101)]);

            let mut map = HashOrderedMap::from([('a', 100), ('b', 101), ('c', 102)]);
            map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);
            map.entry('d').and_move_back();
            map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);
        }
    }

    #[test]
    fn entry_or_func() {
        let mut map = HashOrderedMap::from([]);
        map.assert_map(&[]);

        assert_eq!(map.entry('a').or_default(), &0);
        map.assert_map(&[('a', 0)]);
        assert_eq!(map.entry('a').or_default(), &0);
        map.assert_map(&[('a', 0)]);

        assert_eq!(map.entry('b').or_insert(101), &101);
        map.assert_map(&[('a', 0), ('b', 101)]);
        assert_eq!(map.entry('b').or_insert(1000), &101);
        map.assert_map(&[('a', 0), ('b', 101)]);

        assert_eq!(map.entry('c').or_insert_with(|| 102), &102);
        map.assert_map(&[('a', 0), ('b', 101), ('c', 102)]);
        assert_eq!(map.entry('c').or_insert_with(|| panic!()), &102);
        map.assert_map(&[('a', 0), ('b', 101), ('c', 102)]);

        let f = |key: &char| {
            assert_eq!(key, &'d');
            103
        };
        assert_eq!(map.entry('d').or_insert_with_key(f), &103);
        map.assert_map(&[('a', 0), ('b', 101), ('c', 102), ('d', 103)]);
        assert_eq!(map.entry('d').or_insert_with_key(|_| panic!()), &103);
        map.assert_map(&[('a', 0), ('b', 101), ('c', 102), ('d', 103)]);
    }

    #[test]
    fn entry_insert_entry() {
        let mut map = HashOrderedMap::from([('a', 100), ('b', 101)]);
        map.assert_map(&[('a', 100), ('b', 101)]);

        map.entry('c').insert_entry(102);
        map.assert_map(&[('a', 100), ('b', 101), ('c', 102)]);
        map.entry('b').insert_entry(1101);
        map.assert_map(&[('a', 100), ('b', 1101), ('c', 102)]); // Position is not moved.
    }
}
