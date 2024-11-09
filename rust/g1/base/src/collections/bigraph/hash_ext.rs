use std::borrow::Borrow;
use std::collections::HashSet;
use std::fmt::{self, Debug};
use std::hash::{BuildHasher, Hash};

use super::{
    super::{
        cursor_set::{Cursor, HashCursorSet},
        DefaultHashBuilder,
    },
    hash::NaiveHashBiGraph,
};

#[derive(Clone)]
pub struct HashBiGraph<K, V, KS = DefaultHashBuilder, VS = DefaultHashBuilder> {
    keys: HashCursorSet<K, KS>,
    values: HashCursorSet<V, VS>,
    graph: NaiveHashBiGraph<Cursor, Cursor>,
}

#[derive(Clone)]
pub struct SetView<'a, C, T, S> {
    // This is either a `HashSet<Cursor>` or a reference to it.
    cursors: C,
    elements: &'a HashCursorSet<T, S>,
    removed: HashSet<T>,
}

pub trait CursorSet {
    fn is_empty(&self) -> bool;

    fn len(&self) -> usize;

    fn contains(&self, p: Cursor) -> bool;

    fn iter(&self) -> impl Iterator<Item = Cursor>;
}

impl<K, V, KS, VS> HashBiGraph<K, V, KS, VS> {
    pub fn with_hasher(key_hash_builder: KS, value_hash_builder: VS) -> Self {
        Self {
            keys: HashCursorSet::with_hasher(key_hash_builder),
            values: HashCursorSet::with_hasher(value_hash_builder),
            graph: NaiveHashBiGraph::new(),
        }
    }

    pub fn with_capacity_and_hasher(
        key_capacity: usize,
        value_capacity: usize,
        key_hash_builder: KS,
        value_hash_builder: VS,
    ) -> Self {
        Self {
            keys: HashCursorSet::with_capacity_and_hasher(key_capacity, key_hash_builder),
            values: HashCursorSet::with_capacity_and_hasher(value_capacity, value_hash_builder),
            graph: NaiveHashBiGraph::with_capacity(key_capacity, value_capacity),
        }
    }
}

impl<K, V, KS, VS> Default for HashBiGraph<K, V, KS, VS>
where
    KS: Default,
    VS: Default,
{
    fn default() -> Self {
        Self::with_hasher(Default::default(), Default::default())
    }
}

impl<K, V> HashBiGraph<K, V> {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_capacity(key_capacity: usize, value_capacity: usize) -> Self {
        Self::with_capacity_and_hasher(
            key_capacity,
            value_capacity,
            Default::default(),
            Default::default(),
        )
    }
}

impl<K, V, KS, VS> Extend<(K, V)> for HashBiGraph<K, V, KS, VS>
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

impl<K, V, KS, VS, const N: usize> From<[(K, V); N]> for HashBiGraph<K, V, KS, VS>
where
    K: Eq + Hash,
    V: Eq + Hash,
    KS: BuildHasher + Default,
    VS: BuildHasher + Default,
{
    fn from(arr: [(K, V); N]) -> Self {
        Self::from_iter(arr)
    }
}

impl<K, V, KS, VS> FromIterator<(K, V)> for HashBiGraph<K, V, KS, VS>
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
        let mut graph = Self::default();
        graph.extend(iter);
        graph
    }
}

impl<K, V, KS, VS> Debug for HashBiGraph<K, V, KS, VS>
where
    K: Debug,
    V: Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_map().entries(self.iter()).finish()
    }
}

impl<K, V, KS, VS> PartialEq for HashBiGraph<K, V, KS, VS>
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

impl<K, V, KS, VS> Eq for HashBiGraph<K, V, KS, VS>
where
    K: Eq + Hash,
    V: Eq + Hash,
    KS: BuildHasher,
    VS: BuildHasher,
{
}

impl<K, V, KS, VS> HashBiGraph<K, V, KS, VS> {
    pub fn key_capacity(&self) -> usize {
        self.keys.capacity()
    }

    pub fn value_capacity(&self) -> usize {
        self.values.capacity()
    }

    pub fn is_empty(&self) -> bool {
        self.graph.is_empty()
    }

    /// Returns the number of edges.
    pub fn len(&self) -> usize {
        self.graph.len()
    }

    pub fn num_keys(&self) -> usize {
        self.keys.len()
    }

    pub fn num_values(&self) -> usize {
        self.values.len()
    }

    pub fn keys(&self) -> impl Iterator<Item = &K> {
        self.keys.iter()
    }

    pub fn values(&self) -> impl Iterator<Item = &V> {
        self.values.iter()
    }

    pub fn iter(&self) -> impl Iterator<Item = (&K, &V)> {
        self.graph
            .iter()
            .map(|(k, v)| (&self.keys[k], &self.values[v]))
    }

    pub fn clear(&mut self) {
        self.keys.clear();
        self.values.clear();
        self.graph.clear();
    }
}

impl<K, V, KS, VS> HashBiGraph<K, V, KS, VS>
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
        self.keys.contains(key)
    }

    pub fn contains_value<Q>(&self, value: &Q) -> bool
    where
        V: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.values.contains(value)
    }

    pub fn contains<KQ, VQ>(&self, key: &KQ, value: &VQ) -> bool
    where
        K: Borrow<KQ>,
        KQ: Eq + Hash + ?Sized,
        V: Borrow<VQ>,
        VQ: Eq + Hash + ?Sized,
    {
        let contains: Option<bool> = try {
            self.graph
                .contains(self.keys.find(key)?, self.values.find(value)?)
        };
        contains.unwrap_or(false)
    }

    pub fn get<Q>(&self, key: &Q) -> Option<SetView<'_, &'_ HashSet<Cursor>, V, VS>>
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        Some(SetView::new(
            self.graph.get(self.keys.find(key)?).unwrap(),
            &self.values,
            HashSet::new(),
        ))
    }

    pub fn inverse_get<Q>(&self, value: &Q) -> Option<SetView<'_, &'_ HashSet<Cursor>, K, KS>>
    where
        V: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        Some(SetView::new(
            self.graph.inverse_get(self.values.find(value)?).unwrap(),
            &self.keys,
            HashSet::new(),
        ))
    }

    pub fn insert(&mut self, key: K, value: V) -> bool {
        let (_, p) = self.keys.insert(key);
        let (_, q) = self.values.insert(value);
        self.graph.insert(p, q)
    }

    pub fn remove_key<Q>(&mut self, key: &Q) -> Option<SetView<'_, HashSet<Cursor>, V, VS>>
    where
        K: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        let (mut cursors, isolated) = self
            .graph
            .remove_key_return_isolated(self.keys.remove(key)?)
            .unwrap();
        let removed = remove_many(isolated, &mut cursors, &mut self.values);
        Some(SetView::new(cursors, &self.values, removed))
    }

    pub fn remove_value<Q>(&mut self, value: &Q) -> Option<SetView<'_, HashSet<Cursor>, K, KS>>
    where
        V: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        let (mut cursors, isolated) = self
            .graph
            .remove_value_return_isolated(self.values.remove(value)?)
            .unwrap();
        let removed = remove_many(isolated, &mut cursors, &mut self.keys);
        Some(SetView::new(cursors, &self.keys, removed))
    }

    pub fn remove<KQ, VQ>(&mut self, key: &KQ, value: &VQ) -> bool
    where
        K: Borrow<KQ>,
        KQ: Eq + Hash + ?Sized,
        V: Borrow<VQ>,
        VQ: Eq + Hash + ?Sized,
    {
        let remove: Option<()> = try {
            let p = self.keys.find(key)?;
            let q = self.values.find(value)?;
            let (key_isolated, value_isolated) = self.graph.remove_return_isolated(p, q)?;
            if key_isolated {
                self.keys.remove_cursor(p);
            }
            if value_isolated {
                self.values.remove_cursor(q);
            }
        };
        remove.is_some()
    }
}

fn remove_many<T, S>(
    isolated: Vec<Cursor>,
    cursors: &mut HashSet<Cursor>,
    elements: &mut HashCursorSet<T, S>,
) -> HashSet<T>
where
    T: Eq + Hash,
    S: BuildHasher,
{
    let mut removed = HashSet::new();
    for cursor in isolated {
        assert!(cursors.remove(&cursor));
        assert!(removed.insert(elements.remove_cursor(cursor)));
    }
    removed
}

impl<'a, C, T, S> SetView<'a, C, T, S>
where
    C: CursorSet,
{
    fn new(cursors: C, elements: &'a HashCursorSet<T, S>, removed: HashSet<T>) -> Self {
        assert!(!cursors.is_empty() || !removed.is_empty());
        Self {
            cursors,
            elements,
            removed,
        }
    }
}

impl<C, T, S> Debug for SetView<'_, C, T, S>
where
    C: CursorSet,
    T: Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_set().entries(self.iter()).finish()
    }
}

impl<C, T, S> PartialEq for SetView<'_, C, T, S>
where
    C: CursorSet,
    T: Eq + Hash,
    S: BuildHasher,
{
    fn eq(&self, other: &Self) -> bool {
        self.len() == other.len() && self.iter().all(|e| other.contains(e))
    }
}

impl<C, T, S> SetView<'_, C, T, S>
where
    C: CursorSet,
{
    pub fn is_empty(&self) -> bool {
        self.cursors.is_empty() && self.removed.is_empty()
    }

    pub fn len(&self) -> usize {
        self.cursors.len() + self.removed.len()
    }

    pub fn iter(&self) -> impl Iterator<Item = &T> {
        self.cursors
            .iter()
            .map(|p| &self.elements[p])
            .chain(self.removed.iter())
    }
}

impl<C, T, S> SetView<'_, C, T, S>
where
    C: CursorSet,
    T: Eq + Hash,
    S: BuildHasher,
{
    pub fn contains<Q>(&self, element: &Q) -> bool
    where
        T: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.elements
            .find(element)
            .map(|p| self.cursors.contains(p))
            .unwrap_or(false)
            || self.removed.contains(element)
    }
}

impl CursorSet for HashSet<Cursor> {
    fn is_empty(&self) -> bool {
        self.is_empty()
    }

    fn len(&self) -> usize {
        self.len()
    }

    fn contains(&self, p: Cursor) -> bool {
        self.contains(&p)
    }

    fn iter(&self) -> impl Iterator<Item = Cursor> {
        self.iter().copied()
    }
}

impl CursorSet for &HashSet<Cursor> {
    fn is_empty(&self) -> bool {
        (*self).is_empty()
    }

    fn len(&self) -> usize {
        (*self).len()
    }

    fn contains(&self, p: Cursor) -> bool {
        (*self).contains(&p)
    }

    fn iter(&self) -> impl Iterator<Item = Cursor> {
        (*self).iter().copied()
    }
}

#[cfg(test)]
mod test_harness {
    use crate::iter::IteratorExt;

    use super::*;

    impl HashBiGraph<char, usize> {
        pub fn assert_graph(&self, expect: &[(char, usize)]) {
            assert_eq!(self.is_empty(), expect.is_empty());
            assert_eq!(self.len(), expect.len());

            let expect_keys: HashSet<_> = expect.iter().map(|(k, _)| *k).collect();
            let expect_keys = expect_keys.into_iter().collect_then_sort();
            let expect_values: HashSet<_> = expect.iter().map(|(_, v)| *v).collect();
            let expect_values = expect_values.into_iter().collect_then_sort();
            assert_eq!(self.num_keys(), expect_keys.len());
            assert_eq!(self.num_values(), expect_values.len());
            assert_eq!(self.keys().copied().collect_then_sort(), expect_keys);
            assert_eq!(self.values().copied().collect_then_sort(), expect_values);

            assert_eq!(
                self.iter().map(|(k, v)| (*k, *v)).collect_then_sort(),
                expect.iter().copied().collect_then_sort(),
            );

            for (k, v) in expect {
                assert_eq!(self.contains_key(k), true);
                assert_eq!(self.contains_value(v), true);
                assert_eq!(self.contains(k, v), true);
            }
            for key in &expect_keys {
                let vs: Vec<_> = expect
                    .iter()
                    .filter_map(|(k, v)| (k == key).then_some(*v))
                    .collect();
                self.get(key).unwrap().assert_set(&vs, &[]);
            }
            for value in &expect_values {
                let ks: Vec<_> = expect
                    .iter()
                    .filter_map(|(k, v)| (v == value).then_some(*k))
                    .collect();
                self.inverse_get(value).unwrap().assert_set(&ks, &[]);
            }
        }
    }

    impl<'a, C, T, S> SetView<'a, C, T, S>
    where
        C: CursorSet,
        T: Copy + Debug + Eq + Hash + Ord,
        S: BuildHasher,
    {
        pub fn assert_set(&self, expect: &[T], removed: &[T]) {
            assert_eq!(self.is_empty(), expect.is_empty());
            assert_eq!(self.len(), expect.len());

            assert_eq!(
                self.iter().collect_then_sort(),
                expect.iter().collect_then_sort(),
            );

            for element in expect {
                assert_eq!(self.contains(element), true);
            }

            assert_eq!(
                self.removed.iter().collect_then_sort(),
                removed.iter().collect_then_sort(),
            );

            let elements: HashSet<_> = self.elements.iter().copied().collect();
            assert_eq!(elements.is_disjoint(&self.removed), true);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new() {
        let graph1 = HashBiGraph::new();
        graph1.assert_graph(&[]);
        assert_eq!(graph1.key_capacity(), 0);
        assert_eq!(graph1.value_capacity(), 0);

        let graph2 = HashBiGraph::with_capacity(3, 3);
        graph2.assert_graph(&[]);
        assert_ne!(graph2.key_capacity(), 0);
        assert_ne!(graph2.value_capacity(), 0);

        assert_eq!(graph1, graph2);
        assert_ne!(graph1.key_capacity(), graph2.key_capacity());

        HashBiGraph::default().assert_graph(&[]);

        let expect = [('a', 100)];
        HashBiGraph::from(expect).assert_graph(&expect);
        let expect = [('a', 100), ('c', 102)];
        HashBiGraph::from(expect).assert_graph(&expect);
        let expect = [('a', 100), ('c', 102), ('b', 101)];
        HashBiGraph::from(expect).assert_graph(&expect);
    }

    #[test]
    fn eq() {
        assert_eq!(
            HashBiGraph::<char, usize>::from([('a', 100), ('a', 101), ('b', 101)]),
            HashBiGraph::from([('b', 101), ('a', 101), ('a', 100)]),
        );

        assert_ne!(
            HashBiGraph::<char, usize>::from([('a', 100)]),
            HashBiGraph::from([('b', 101), ('a', 100)]),
        );
        assert_ne!(
            HashBiGraph::<char, usize>::from([('a', 101), ('b', 100)]),
            HashBiGraph::from([('b', 101), ('a', 100)]),
        );
    }

    #[test]
    fn clear() {
        let mut graph = HashBiGraph::from([('a', 100), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('b', 101)]);

        graph.clear();
        graph.assert_graph(&[]);
    }

    #[test]
    fn contains_and_get() {
        let graph = HashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(graph.contains_key(&'a'), true);
        assert_eq!(graph.contains_key(&'b'), true);
        assert_eq!(graph.contains_key(&'c'), false);

        assert_eq!(graph.contains_value(&100), true);
        assert_eq!(graph.contains_value(&101), true);
        assert_eq!(graph.contains_value(&102), false);

        assert_eq!(graph.contains(&'a', &100), true);
        assert_eq!(graph.contains(&'a', &101), true);
        assert_eq!(graph.contains(&'a', &102), false);
        assert_eq!(graph.contains(&'b', &101), true);
        assert_eq!(graph.contains(&'b', &100), false);

        graph.get(&'a').unwrap().assert_set(&[100, 101], &[]);
        graph.get(&'b').unwrap().assert_set(&[101], &[]);
        assert_eq!(graph.get(&'c'), None);

        graph.inverse_get(&100).unwrap().assert_set(&['a'], &[]);
        graph
            .inverse_get(&101)
            .unwrap()
            .assert_set(&['a', 'b'], &[]);
        assert_eq!(graph.inverse_get(&102), None);
    }

    #[test]
    fn insert() {
        let mut graph = HashBiGraph::new();
        graph.assert_graph(&[]);

        assert_eq!(graph.insert('a', 100), true);
        graph.assert_graph(&[('a', 100)]);
        assert_eq!(graph.insert('a', 100), false);
        graph.assert_graph(&[('a', 100)]);

        assert_eq!(graph.insert('a', 101), true);
        graph.assert_graph(&[('a', 100), ('a', 101)]);
    }

    #[test]
    fn remove_key() {
        let mut graph = HashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(graph.remove_key(&'c'), None);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        graph
            .remove_key(&'a')
            .unwrap()
            .assert_set(&[100, 101], &[100]);
        graph.assert_graph(&[('b', 101)]);
        assert_eq!(graph.remove_key(&'a'), None);
        graph.assert_graph(&[('b', 101)]);

        let mut graph = HashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        graph.remove_key(&'b').unwrap().assert_set(&[101], &[]);
        graph.assert_graph(&[('a', 100), ('a', 101)]);
    }

    #[test]
    fn remove_value() {
        let mut graph = HashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(graph.remove_value(&102), None);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        graph.remove_value(&100).unwrap().assert_set(&['a'], &[]);
        graph.assert_graph(&[('a', 101), ('b', 101)]);
        assert_eq!(graph.remove_value(&100), None);
        graph.assert_graph(&[('a', 101), ('b', 101)]);

        let mut graph = HashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        graph
            .remove_value(&101)
            .unwrap()
            .assert_set(&['a', 'b'], &['b']);
        graph.assert_graph(&[('a', 100)]);
    }

    #[test]
    fn remove() {
        let mut graph = HashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(graph.remove(&'c', &100), false);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);
        assert_eq!(graph.remove(&'a', &102), false);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);
        assert_eq!(graph.remove(&'c', &102), false);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(graph.remove(&'a', &100), true);
        graph.assert_graph(&[('a', 101), ('b', 101)]);
        assert_eq!(graph.remove(&'a', &100), false);
        graph.assert_graph(&[('a', 101), ('b', 101)]);

        let mut graph = HashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(graph.remove(&'a', &101), true);
        graph.assert_graph(&[('a', 100), ('b', 101)]);

        assert_eq!(graph.remove(&'a', &100), true);
        graph.assert_graph(&[('b', 101)]);

        let mut graph = HashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(graph.remove(&'b', &101), true);
        graph.assert_graph(&[('a', 100), ('a', 101)]);
    }
}
