use std::collections::{hash_map::Entry, HashMap, HashSet};
use std::fmt::{self, Debug};
use std::hash::Hash;

/// `NaiveHashBiGraph`
///
/// It is naive because it requires both `K: Copy` and `V: Copy`.
#[derive(Clone)]
pub struct NaiveHashBiGraph<K, V> {
    graph: HashMap<K, HashSet<V>>,
    inverse: HashMap<V, HashSet<K>>,
}

impl<K, V> NaiveHashBiGraph<K, V> {
    pub fn new() -> Self {
        Self {
            graph: HashMap::new(),
            inverse: HashMap::new(),
        }
    }

    pub fn with_capacity(key_capacity: usize, value_capacity: usize) -> Self {
        Self {
            graph: HashMap::with_capacity(key_capacity),
            inverse: HashMap::with_capacity(value_capacity),
        }
    }
}

impl<K, V> Default for NaiveHashBiGraph<K, V> {
    fn default() -> Self {
        Self::new()
    }
}

impl<K, V> Extend<(K, V)> for NaiveHashBiGraph<K, V>
where
    K: Copy + Eq + Hash,
    V: Copy + Eq + Hash,
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

impl<K, V, const N: usize> From<[(K, V); N]> for NaiveHashBiGraph<K, V>
where
    K: Copy + Eq + Hash,
    V: Copy + Eq + Hash,
{
    fn from(arr: [(K, V); N]) -> Self {
        Self::from_iter(arr)
    }
}

impl<K, V> FromIterator<(K, V)> for NaiveHashBiGraph<K, V>
where
    K: Copy + Eq + Hash,
    V: Copy + Eq + Hash,
{
    fn from_iter<I>(iter: I) -> Self
    where
        I: IntoIterator<Item = (K, V)>,
    {
        let mut graph = Self::new();
        graph.extend(iter);
        graph
    }
}

impl<K, V> Debug for NaiveHashBiGraph<K, V>
where
    K: Copy + Debug,
    V: Copy + Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_map().entries(self.iter()).finish()
    }
}

impl<K, V> PartialEq for NaiveHashBiGraph<K, V>
where
    K: Eq + Hash,
    V: Eq + Hash,
{
    fn eq(&self, other: &Self) -> bool {
        self.graph == other.graph
    }
}

impl<K, V> Eq for NaiveHashBiGraph<K, V>
where
    K: Eq + Hash,
    V: Eq + Hash,
{
}

impl<K, V> NaiveHashBiGraph<K, V> {
    pub fn key_capacity(&self) -> usize {
        self.graph.capacity()
    }

    pub fn value_capacity(&self) -> usize {
        self.inverse.capacity()
    }

    pub fn is_empty(&self) -> bool {
        self.graph.is_empty()
    }

    /// Returns the number of edges.
    pub fn len(&self) -> usize {
        self.graph.values().map(|vs| vs.len()).sum()
    }

    pub fn num_keys(&self) -> usize {
        self.graph.len()
    }

    pub fn num_values(&self) -> usize {
        self.inverse.len()
    }

    pub fn clear(&mut self) {
        self.graph.clear();
        self.inverse.clear();
    }
}

impl<K, V> NaiveHashBiGraph<K, V>
where
    K: Copy,
    V: Copy,
{
    pub fn keys(&self) -> impl Iterator<Item = K> + '_ {
        self.graph.keys().copied()
    }

    pub fn values(&self) -> impl Iterator<Item = V> + '_ {
        self.inverse.keys().copied()
    }

    pub fn iter(&self) -> impl Iterator<Item = (K, V)> + '_ {
        self.graph
            .iter()
            .flat_map(|(&k, vs)| vs.iter().map(move |&v| (k, v)))
    }
}

impl<K, V> NaiveHashBiGraph<K, V>
where
    K: Copy + Eq + Hash,
    V: Copy + Eq + Hash,
{
    pub fn contains_key(&self, key: K) -> bool {
        self.graph.contains_key(&key)
    }

    pub fn contains_value(&self, value: V) -> bool {
        self.inverse.contains_key(&value)
    }

    pub fn contains(&self, key: K, value: V) -> bool {
        self.graph
            .get(&key)
            .map(|vs| vs.contains(&value))
            .unwrap_or(false)
    }

    pub fn get(&self, key: K) -> Option<&HashSet<V>> {
        self.graph.get(&key)
    }

    pub fn inverse_get(&self, value: V) -> Option<&HashSet<K>> {
        self.inverse.get(&value)
    }

    // TODO: Provide an `entry` method equivalent to `HashMap::entry`.

    pub fn insert(&mut self, key: K, value: V) -> bool {
        let didnt_have_value = self.graph.entry(key).or_default().insert(value);
        let didnt_have_key = self.inverse.entry(value).or_default().insert(key);
        assert_eq!(didnt_have_value, didnt_have_key);
        didnt_have_value
    }

    pub fn remove_key(&mut self, key: K) -> Option<HashSet<V>> {
        self.remove_key_return_isolated(key).map(|(vs, _)| vs)
    }

    pub fn remove_key_return_isolated(&mut self, key: K) -> Option<(HashSet<V>, Vec<V>)> {
        let vs = self.graph.remove(&key)?;
        let isolated = vs
            .iter()
            .copied()
            .filter(|&v| remove(&mut self.inverse, v, key).unwrap())
            .collect();
        Some((vs, isolated))
    }

    pub fn remove_value(&mut self, value: V) -> Option<HashSet<K>> {
        self.remove_value_return_isolated(value).map(|(ks, _)| ks)
    }

    pub fn remove_value_return_isolated(&mut self, value: V) -> Option<(HashSet<K>, Vec<K>)> {
        let ks = self.inverse.remove(&value)?;
        let isolated = ks
            .iter()
            .copied()
            .filter(|&k| remove(&mut self.graph, k, value).unwrap())
            .collect();
        Some((ks, isolated))
    }

    pub fn remove(&mut self, key: K, value: V) -> bool {
        self.remove_return_isolated(key, value).is_some()
    }

    pub fn remove_return_isolated(&mut self, key: K, value: V) -> Option<(bool, bool)> {
        let key_isolated = remove(&mut self.graph, key, value)?;
        let value_isolated = remove(&mut self.inverse, value, key).unwrap();
        Some((key_isolated, value_isolated))
    }
}

/// Removes `(p, q)` and then removes `p` if it becomes isolated.
fn remove<P, Q>(graph: &mut HashMap<P, HashSet<Q>>, p: P, q: Q) -> Option<bool>
where
    P: Copy + Eq + Hash,
    Q: Copy + Eq + Hash,
{
    let mut entry = match graph.entry(p) {
        Entry::Occupied(entry) => entry,
        Entry::Vacant(_) => return None,
    };
    let qs = entry.get_mut();
    if !qs.remove(&q) {
        return None;
    }
    let isolated = qs.is_empty();
    if isolated {
        entry.remove();
    }
    Some(isolated)
}

#[cfg(test)]
mod test_harness {
    use crate::iter::IteratorExt;

    use super::*;

    impl NaiveHashBiGraph<char, usize> {
        pub fn assert_graph(&self, expect: &[(char, usize)]) {
            assert_eq!(self.is_empty(), expect.is_empty());
            assert_eq!(self.len(), expect.len());

            let expect_keys: HashSet<_> = expect.iter().map(|(k, _)| *k).collect();
            let expect_keys = expect_keys.into_iter().collect_then_sort();
            let expect_values: HashSet<_> = expect.iter().map(|(_, v)| *v).collect();
            let expect_values = expect_values.into_iter().collect_then_sort();
            assert_eq!(self.num_keys(), expect_keys.len());
            assert_eq!(self.num_values(), expect_values.len());
            assert_eq!(self.keys().collect_then_sort(), expect_keys);
            assert_eq!(self.values().collect_then_sort(), expect_values);

            assert_eq!(
                self.iter().collect_then_sort(),
                expect.iter().copied().collect_then_sort(),
            );

            for &(k, v) in expect {
                assert_eq!(self.contains_key(k), true);
                assert_eq!(self.contains_value(v), true);
                assert_eq!(self.contains(k, v), true);
            }
            for k in expect_keys {
                assert_eq!(self.get(k).is_some(), true);
            }
            for v in expect_values {
                assert_eq!(self.inverse_get(v).is_some(), true);
            }

            let mut graph = HashMap::<_, HashSet<_>>::new();
            let mut inverse = HashMap::<_, HashSet<_>>::new();
            for &(k, v) in expect {
                graph.entry(k).or_default().insert(v);
                inverse.entry(v).or_default().insert(k);
            }
            assert_eq!(self.graph, graph);
            assert_eq!(self.inverse, inverse);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new() {
        let graph1 = NaiveHashBiGraph::new();
        graph1.assert_graph(&[]);
        assert_eq!(graph1.key_capacity(), 0);
        assert_eq!(graph1.value_capacity(), 0);

        let graph2 = NaiveHashBiGraph::with_capacity(3, 3);
        graph2.assert_graph(&[]);
        assert_ne!(graph2.key_capacity(), 0);
        assert_ne!(graph2.value_capacity(), 0);

        assert_eq!(graph1, graph2);
        assert_ne!(graph1.key_capacity(), graph2.key_capacity());

        NaiveHashBiGraph::default().assert_graph(&[]);

        let expect = [('a', 100)];
        NaiveHashBiGraph::from(expect).assert_graph(&expect);
        let expect = [('a', 100), ('c', 102)];
        NaiveHashBiGraph::from(expect).assert_graph(&expect);
        let expect = [('a', 100), ('c', 102), ('b', 101)];
        NaiveHashBiGraph::from(expect).assert_graph(&expect);
    }

    #[test]
    fn eq() {
        assert_eq!(
            NaiveHashBiGraph::<char, usize>::from([('a', 100), ('a', 101), ('b', 101)]),
            NaiveHashBiGraph::from([('b', 101), ('a', 101), ('a', 100)]),
        );

        assert_ne!(
            NaiveHashBiGraph::<char, usize>::from([('a', 100)]),
            NaiveHashBiGraph::from([('b', 101), ('a', 100)]),
        );
        assert_ne!(
            NaiveHashBiGraph::<char, usize>::from([('a', 101), ('b', 100)]),
            NaiveHashBiGraph::from([('b', 101), ('a', 100)]),
        );
    }

    #[test]
    fn clear() {
        let mut graph = NaiveHashBiGraph::from([('a', 100), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('b', 101)]);

        graph.clear();
        graph.assert_graph(&[]);
    }

    #[test]
    fn contains_and_get() {
        let graph = NaiveHashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(graph.contains_key('a'), true);
        assert_eq!(graph.contains_key('b'), true);
        assert_eq!(graph.contains_key('c'), false);

        assert_eq!(graph.contains_value(100), true);
        assert_eq!(graph.contains_value(101), true);
        assert_eq!(graph.contains_value(102), false);

        assert_eq!(graph.contains('a', 100), true);
        assert_eq!(graph.contains('a', 101), true);
        assert_eq!(graph.contains('a', 102), false);
        assert_eq!(graph.contains('b', 101), true);
        assert_eq!(graph.contains('b', 100), false);

        assert_eq!(graph.get('a'), Some(&HashSet::from([100, 101])));
        assert_eq!(graph.get('b'), Some(&HashSet::from([101])));
        assert_eq!(graph.get('c'), None);

        assert_eq!(graph.inverse_get(100), Some(&HashSet::from(['a'])));
        assert_eq!(graph.inverse_get(101), Some(&HashSet::from(['a', 'b'])));
        assert_eq!(graph.inverse_get(102), None);
    }

    #[test]
    fn insert() {
        let mut graph = NaiveHashBiGraph::new();
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
        let mut graph = NaiveHashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(graph.remove_key_return_isolated('c'), None);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(
            graph.remove_key_return_isolated('a'),
            Some((HashSet::from([100, 101]), vec![100])),
        );
        graph.assert_graph(&[('b', 101)]);
        assert_eq!(graph.remove_key_return_isolated('a'), None);
        graph.assert_graph(&[('b', 101)]);

        let mut graph = NaiveHashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(
            graph.remove_key_return_isolated('b'),
            Some((HashSet::from([101]), vec![])),
        );
        graph.assert_graph(&[('a', 100), ('a', 101)]);
    }

    #[test]
    fn remove_value() {
        let mut graph = NaiveHashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(graph.remove_value_return_isolated(102), None);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(
            graph.remove_value_return_isolated(100),
            Some((HashSet::from(['a']), vec![])),
        );
        graph.assert_graph(&[('a', 101), ('b', 101)]);
        assert_eq!(graph.remove_value_return_isolated(100), None);
        graph.assert_graph(&[('a', 101), ('b', 101)]);

        let mut graph = NaiveHashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(
            graph.remove_value_return_isolated(101),
            Some((HashSet::from(['a', 'b']), vec!['b'])),
        );
        graph.assert_graph(&[('a', 100)]);
    }

    #[test]
    fn remove() {
        let mut graph = NaiveHashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(graph.remove_return_isolated('c', 100), None);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);
        assert_eq!(graph.remove_return_isolated('a', 102), None);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);
        assert_eq!(graph.remove_return_isolated('c', 102), None);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(graph.remove_return_isolated('a', 100), Some((false, true)));
        graph.assert_graph(&[('a', 101), ('b', 101)]);
        assert_eq!(graph.remove_return_isolated('a', 100), None);
        graph.assert_graph(&[('a', 101), ('b', 101)]);

        let mut graph = NaiveHashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(graph.remove_return_isolated('a', 101), Some((false, false)));
        graph.assert_graph(&[('a', 100), ('b', 101)]);

        assert_eq!(graph.remove_return_isolated('a', 100), Some((true, true)));
        graph.assert_graph(&[('b', 101)]);

        let mut graph = NaiveHashBiGraph::from([('a', 100), ('a', 101), ('b', 101)]);
        graph.assert_graph(&[('a', 100), ('a', 101), ('b', 101)]);

        assert_eq!(graph.remove_return_isolated('b', 101), Some((true, false)));
        graph.assert_graph(&[('a', 100), ('a', 101)]);
    }
}
