//! `Table` but with `BiMap`-like constraints.
//!
//! In analogy, a `Table` is a matrix, and a `BiTable` is a generalized permutation matrix.

use std::borrow::Borrow;
use std::fmt::{self, Debug};
use std::hash::{BuildHasher, Hash};

use super::{
    DefaultHashBuilder,
    index_map::{AsHash, HashIndexMap},
    vec_list::{Cursor, VecList},
};

#[derive(Clone)]
pub struct HashBasedBiTable<R, C, V, RS = DefaultHashBuilder, CS = DefaultHashBuilder> {
    row_map: HashIndexMap<Cursor, RowAsHash, (R, C, V), R, RS>,
    column_map: HashIndexMap<Cursor, ColumnAsHash, (R, C, V), C, CS>,
    entries: VecList<(R, C, V)>,
}

fn to_r<R, C, V>((r, _, _): &(R, C, V)) -> &R {
    r
}

fn to_c<R, C, V>((_, c, _): &(R, C, V)) -> &C {
    c
}

fn to_v<R, C, V>((_, _, v): &(R, C, V)) -> &V {
    v
}

fn to_v_mut<R, C, V>((_, _, v): &mut (R, C, V)) -> &mut V {
    v
}

fn to_rv<R, C, V>((r, _, v): &(R, C, V)) -> (&R, &V) {
    (r, v)
}

fn to_rv_mut<R, C, V>((r, _, v): &mut (R, C, V)) -> (&R, &mut V) {
    (r, v)
}

fn to_cv<R, C, V>((_, c, v): &(R, C, V)) -> (&C, &V) {
    (c, v)
}

fn to_cv_mut<R, C, V>((_, c, v): &mut (R, C, V)) -> (&C, &mut V) {
    (c, v)
}

fn to_rcv<R, C, V>((r, c, v): &(R, C, V)) -> (&R, &C, &V) {
    (r, c, v)
}

fn to_rcv_mut<R, C, V>((r, c, v): &mut (R, C, V)) -> (&R, &C, &mut V) {
    (r, c, v)
}

fn into_v<R, C, V>((_, _, v): (R, C, V)) -> V {
    v
}

fn into_rv<R, C, V>((r, _, v): (R, C, V)) -> (R, V) {
    (r, v)
}

fn into_cv<R, C, V>((_, c, v): (R, C, V)) -> (C, V) {
    (c, v)
}

#[derive(Clone, Debug)]
struct RowAsHash;

#[derive(Clone, Debug)]
struct ColumnAsHash;

impl<R, C, V> AsHash<(R, C, V), R> for RowAsHash
where
    R: Eq + Hash,
{
    fn as_hash(t: &(R, C, V)) -> &R {
        to_r(t)
    }
}

impl<R, C, V> AsHash<(R, C, V), C> for ColumnAsHash
where
    C: Eq + Hash,
{
    fn as_hash(t: &(R, C, V)) -> &C {
        to_c(t)
    }
}

impl<R, C, V, RS, CS> HashBasedBiTable<R, C, V, RS, CS> {
    pub fn with_hasher(row_hash_builder: RS, column_hash_builder: CS) -> Self {
        Self {
            row_map: HashIndexMap::with_hasher(row_hash_builder),
            column_map: HashIndexMap::with_hasher(column_hash_builder),
            entries: VecList::new(),
        }
    }

    pub fn with_capacity_and_hasher(
        capacity: usize,
        row_hash_builder: RS,
        column_hash_builder: CS,
    ) -> Self {
        Self {
            row_map: HashIndexMap::with_capacity_and_hasher(capacity, row_hash_builder),
            column_map: HashIndexMap::with_capacity_and_hasher(capacity, column_hash_builder),
            entries: VecList::with_capacity(capacity),
        }
    }
}

impl<R, C, V, RS, CS> Default for HashBasedBiTable<R, C, V, RS, CS>
where
    RS: Default,
    CS: Default,
{
    fn default() -> Self {
        Self::with_hasher(Default::default(), Default::default())
    }
}

impl<R, C, V> HashBasedBiTable<R, C, V> {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_capacity(capacity: usize) -> Self {
        Self::with_capacity_and_hasher(capacity, Default::default(), Default::default())
    }
}

impl<R, C, V, RS, CS> Extend<(R, C, V)> for HashBasedBiTable<R, C, V, RS, CS>
where
    R: Eq + Hash,
    C: Eq + Hash,
    RS: BuildHasher,
    CS: BuildHasher,
{
    fn extend<I>(&mut self, iter: I)
    where
        I: IntoIterator<Item = (R, C, V)>,
    {
        for (r, c, v) in iter {
            let _ = self.insert(r, c, v);
        }
    }
}

impl<R, C, V, RS, CS, const N: usize> From<[(R, C, V); N]> for HashBasedBiTable<R, C, V, RS, CS>
where
    R: Eq + Hash,
    C: Eq + Hash,
    RS: BuildHasher + Default,
    CS: BuildHasher + Default,
{
    fn from(arr: [(R, C, V); N]) -> Self {
        let mut table = Self::with_capacity_and_hasher(N, Default::default(), Default::default());
        table.extend(arr);
        table
    }
}

impl<R, C, V, RS, CS> FromIterator<(R, C, V)> for HashBasedBiTable<R, C, V, RS, CS>
where
    R: Eq + Hash,
    C: Eq + Hash,
    RS: BuildHasher + Default,
    CS: BuildHasher + Default,
{
    fn from_iter<I>(iter: I) -> Self
    where
        I: IntoIterator<Item = (R, C, V)>,
    {
        let mut table = Self::default();
        table.extend(iter);
        table
    }
}

impl<R, C, V, RS, CS> Debug for HashBasedBiTable<R, C, V, RS, CS>
where
    R: Debug,
    C: Debug,
    V: Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_map()
            .entries(self.iter().map(|(r, c, v)| ((r, c), v)))
            .finish()
    }
}

impl<R, C, V, RS, CS> PartialEq for HashBasedBiTable<R, C, V, RS, CS>
where
    R: Eq + Hash,
    C: Eq + Hash,
    V: PartialEq,
    RS: BuildHasher,
    CS: BuildHasher,
{
    fn eq(&self, other: &Self) -> bool {
        self.len() == other.len() && self.iter().all(|(r, c, v)| other.get(r, c) == Some(v))
    }
}

impl<R, C, V, RS, CS> Eq for HashBasedBiTable<R, C, V, RS, CS>
where
    R: Eq + Hash,
    C: Eq + Hash,
    V: Eq,
    RS: BuildHasher,
    CS: BuildHasher,
{
}

impl<R, C, V, RS, CS> HashBasedBiTable<R, C, V, RS, CS> {
    pub fn capacity(&self) -> usize {
        self.entries.capacity()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn rows(&self) -> impl Iterator<Item = &R> {
        self.entries.iter().map(to_r)
    }

    pub fn columns(&self) -> impl Iterator<Item = &C> {
        self.entries.iter().map(to_c)
    }

    pub fn values(&self) -> impl Iterator<Item = &V> {
        self.entries.iter().map(to_v)
    }

    pub fn values_mut(&mut self) -> impl Iterator<Item = &mut V> {
        self.entries.iter_mut().map(to_v_mut)
    }

    pub fn iter(&self) -> impl Iterator<Item = (&R, &C, &V)> {
        self.entries.iter().map(to_rcv)
    }

    pub fn iter_mut(&mut self) -> impl Iterator<Item = (&R, &C, &mut V)> {
        self.entries.iter_mut().map(to_rcv_mut)
    }

    pub fn clear(&mut self) {
        self.row_map.clear();
        self.column_map.clear();
        self.entries.clear();
    }
}

impl<R, C, V, RS, CS> HashBasedBiTable<R, C, V, RS, CS>
where
    R: Eq + Hash,
    C: Eq + Hash,
    RS: BuildHasher,
    CS: BuildHasher,
{
    pub fn contains_row<Q>(&self, row: &Q) -> bool
    where
        R: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.row_map.get(&self.entries, row).is_some()
    }

    pub fn contains_column<Q>(&self, column: &Q) -> bool
    where
        C: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.column_map.get(&self.entries, column).is_some()
    }

    pub fn contains<RQ, CQ>(&self, row: &RQ, column: &CQ) -> bool
    where
        R: Borrow<RQ>,
        RQ: Eq + Hash + ?Sized,
        C: Borrow<CQ>,
        CQ: Eq + Hash + ?Sized, // TODO: Should we omit `Hash`?
    {
        self.row_map
            .get(&self.entries, row)
            .is_some_and(|i| to_c(&self.entries[i]).borrow() == column)
    }

    pub fn get_row<Q>(&self, row: &Q) -> Option<(&C, &V)>
    where
        R: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.row_map
            .get(&self.entries, row)
            .map(|i| to_cv(&self.entries[i]))
    }

    pub fn get_row_mut<Q>(&mut self, row: &Q) -> Option<(&C, &mut V)>
    where
        R: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.row_map
            .get(&self.entries, row)
            .map(|i| to_cv_mut(&mut self.entries[i]))
    }

    pub fn get_column<Q>(&self, column: &Q) -> Option<(&R, &V)>
    where
        C: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.column_map
            .get(&self.entries, column)
            .map(|j| to_rv(&self.entries[j]))
    }

    pub fn get_column_mut<Q>(&mut self, column: &Q) -> Option<(&R, &mut V)>
    where
        C: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.column_map
            .get(&self.entries, column)
            .map(|j| to_rv_mut(&mut self.entries[j]))
    }

    pub fn get<RQ, CQ>(&self, row: &RQ, column: &CQ) -> Option<&V>
    where
        R: Borrow<RQ>,
        RQ: Eq + Hash + ?Sized,
        C: Borrow<CQ>,
        CQ: Eq + Hash + ?Sized, // TODO: Should we omit `Hash`?
    {
        self.get_row(row)
            .and_then(|(c, v)| (c.borrow() == column).then_some(v))
    }

    pub fn get_mut<RQ, CQ>(&mut self, row: &RQ, column: &CQ) -> Option<&mut V>
    where
        R: Borrow<RQ>,
        RQ: Eq + Hash + ?Sized,
        C: Borrow<CQ>,
        CQ: Eq + Hash + ?Sized, // TODO: Should we omit `Hash`?
    {
        self.get_row_mut(row)
            .and_then(|(c, v)| (c.borrow() == column).then_some(v))
    }

    // TODO: Provide an `entry` method equivalent to `HashMap::entry`.

    #[allow(clippy::type_complexity)]
    pub fn insert(
        &mut self,
        row: R,
        column: C,
        value: V,
    ) -> Result<(R, C, V), (Option<(C, V)>, Option<(R, V)>)> {
        // TODO: "remove-then-insert" is a simple (and perhaps the only correct) implementation.
        // Is it possible to find a more efficient implementation?

        let i = self.row_map.remove(&self.entries, &row);
        let j = self.column_map.remove(&self.entries, &column);
        let old = match (i, j) {
            (Some(i), Some(j)) if i == j => Ok(self.entries.remove(i)),
            _ => Err((
                i.map(|i| {
                    self.remove_i(i);
                    into_cv(self.entries.remove(i))
                }),
                j.map(|j| {
                    self.remove_j(j);
                    into_rv(self.entries.remove(j))
                }),
            )),
        };

        let k = self.entries.push_back((row, column, value));
        assert_eq!(
            self.row_map
                .insert(&self.entries, to_r(&self.entries[k]), k),
            None,
        );
        assert_eq!(
            self.column_map
                .insert(&self.entries, to_c(&self.entries[k]), k),
            None,
        );

        old
    }

    pub fn remove_row<Q>(&mut self, row: &Q) -> Option<(C, V)>
    where
        R: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        let i = self.row_map.remove(&self.entries, row)?;
        self.remove_i(i);
        Some(into_cv(self.entries.remove(i)))
    }

    pub fn remove_column<Q>(&mut self, column: &Q) -> Option<(R, V)>
    where
        C: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        let j = self.column_map.remove(&self.entries, column)?;
        self.remove_j(j);
        Some(into_rv(self.entries.remove(j)))
    }

    pub fn remove<RQ, CQ>(&mut self, row: &RQ, column: &CQ) -> Option<V>
    where
        R: Borrow<RQ>,
        RQ: Eq + Hash + ?Sized,
        C: Borrow<CQ>,
        CQ: Eq + Hash + ?Sized,
    {
        let r = self.row_map.find_entry(&self.entries, row)?;
        let c = self.column_map.find_entry(&self.entries, column)?;
        let i = *r.get();
        (i == *c.get()).then(|| {
            r.remove();
            c.remove();
            into_v(self.entries.remove(i))
        })
    }

    fn remove_i(&mut self, i: Cursor) {
        assert_eq!(
            self.column_map
                .remove(&self.entries, to_c(&self.entries[i])),
            Some(i),
        );
    }

    fn remove_j(&mut self, j: Cursor) {
        assert_eq!(
            self.row_map.remove(&self.entries, to_r(&self.entries[j])),
            Some(j),
        );
    }
}

#[cfg(test)]
mod test_harness {
    use crate::iter::IteratorExt;

    use super::*;

    impl HashBasedBiTable<char, char, usize> {
        pub fn assert_table(&self, expect: &[(char, char, usize)]) {
            assert_eq!(self.is_empty(), expect.is_empty());
            assert_eq!(self.len(), expect.len());

            assert_eq!(
                self.rows().collect_then_sort(),
                expect.iter().map(to_r).collect_then_sort(),
            );
            assert_eq!(
                self.columns().collect_then_sort(),
                expect.iter().map(to_c).collect_then_sort(),
            );
            assert_eq!(
                self.values().collect_then_sort(),
                expect.iter().map(to_v).collect_then_sort(),
            );
            assert_eq!(
                self.iter().collect_then_sort(),
                expect.iter().map(to_rcv).collect_then_sort(),
            );

            for (r, c, v) in expect {
                assert_eq!(self.contains_row(r), true);
                assert_eq!(self.contains_column(c), true);
                assert_eq!(self.contains(r, c), true);
                assert_eq!(self.get_row(r), Some((c, v)));
                assert_eq!(self.get_column(c), Some((r, v)));
                assert_eq!(self.get(r, c), Some(v));
            }

            self.assert_cursors();
        }

        pub fn assert_cursors(&self) {
            let mut cursors = Vec::new();
            let mut p = self.entries.cursor_front();
            while let Some(cursor) = p {
                cursors.push(usize::from(cursor));
                p = self.entries.next(cursor);
            }
            cursors.sort();

            assert_eq!(
                self.row_map.iter().map(usize::from).collect_then_sort(),
                cursors,
            );

            assert_eq!(
                self.column_map.iter().map(usize::from).collect_then_sort(),
                cursors,
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use std::iter;

    use super::*;

    #[test]
    fn new() {
        let table1 = HashBasedBiTable::new();
        table1.assert_table(&[]);
        assert_eq!(table1.capacity(), 0);

        let table2 = HashBasedBiTable::with_capacity(4);
        table2.assert_table(&[]);
        assert_eq!(table2.capacity(), 4);

        assert_eq!(table1, table2);
        assert_ne!(table1.capacity(), table2.capacity());

        HashBasedBiTable::default().assert_table(&[]);

        let expect = [('a', 'x', 100)];
        HashBasedBiTable::from(expect).assert_table(&expect);
        let expect = [('a', 'x', 100), ('c', 'z', 102)];
        HashBasedBiTable::from(expect).assert_table(&expect);
        let expect = [('a', 'x', 100), ('c', 'z', 102), ('b', 'y', 101)];
        HashBasedBiTable::from(expect).assert_table(&expect);
    }

    #[test]
    fn eq() {
        let table = HashBasedBiTable::<char, char, usize>::from([('a', 'x', 100), ('b', 'y', 101)]);
        assert_eq!(
            table,
            HashBasedBiTable::from([('b', 'y', 101), ('a', 'x', 100)]),
        );

        assert_ne!(table, HashBasedBiTable::from([('a', 'x', 100)]));
        assert_ne!(
            table,
            HashBasedBiTable::from([('b', 'x', 100), ('a', 'y', 101)]),
        );
        assert_ne!(
            table,
            HashBasedBiTable::from([('a', 'y', 100), ('b', 'x', 101)]),
        );
        assert_ne!(
            table,
            HashBasedBiTable::from([('a', 'x', 101), ('b', 'y', 100)]),
        );
    }

    #[test]
    fn clear() {
        let expect = [('a', 'x', 100), ('b', 'y', 101)];
        let mut table = HashBasedBiTable::from(expect);
        table.assert_table(&expect);

        table.clear();
        table.assert_table(&[]);
    }

    #[test]
    fn contains_and_get() {
        let expect = [('a', 'x', 100), ('b', 'y', 101)];
        let table = HashBasedBiTable::from(expect);
        table.assert_table(&expect);

        assert_eq!(table.contains_row(&'a'), true);
        assert_eq!(table.contains_row(&'b'), true);
        assert_eq!(table.contains_row(&'c'), false);

        assert_eq!(table.contains_column(&'x'), true);
        assert_eq!(table.contains_column(&'y'), true);
        assert_eq!(table.contains_column(&'z'), false);

        assert_eq!(table.contains(&'a', &'x'), true);
        assert_eq!(table.contains(&'b', &'y'), true);
        assert_eq!(table.contains(&'a', &'y'), false);
        assert_eq!(table.contains(&'a', &'z'), false);
        assert_eq!(table.contains(&'c', &'x'), false);
        assert_eq!(table.contains(&'c', &'z'), false);

        assert_eq!(table.get_row(&'a'), Some((&'x', &100)));
        assert_eq!(table.get_row(&'b'), Some((&'y', &101)));
        assert_eq!(table.get_row(&'c'), None);

        assert_eq!(table.get_column(&'x'), Some((&'a', &100)));
        assert_eq!(table.get_column(&'y'), Some((&'b', &101)));
        assert_eq!(table.get_column(&'z'), None);

        assert_eq!(table.get(&'a', &'x'), Some(&100));
        assert_eq!(table.get(&'b', &'y'), Some(&101));
        assert_eq!(table.get(&'a', &'y'), None);
        assert_eq!(table.get(&'a', &'z'), None);
        assert_eq!(table.get(&'c', &'x'), None);
        assert_eq!(table.get(&'c', &'z'), None);
    }

    #[test]
    fn insert() {
        let mut table = HashBasedBiTable::new();
        table.assert_table(&[]);

        assert_eq!(table.insert('a', 'x', 200), Err((None, None)));
        table.assert_table(&[('a', 'x', 200)]);
        assert_eq!(table.insert('a', 'x', 100), Ok(('a', 'x', 200)));
        table.assert_table(&[('a', 'x', 100)]);

        assert_eq!(table.insert('a', 'y', 101), Err((Some(('x', 100)), None)));
        table.assert_table(&[('a', 'y', 101)]);

        assert_eq!(table.insert('b', 'y', 102), Err((None, Some(('a', 101)))));
        table.assert_table(&[('b', 'y', 102)]);

        let mut table = HashBasedBiTable::from([('a', 'x', 100), ('b', 'y', 101)]);
        table.assert_table(&[('a', 'x', 100), ('b', 'y', 101)]);
        assert_eq!(
            table.insert('a', 'y', 102),
            Err((Some(('x', 100)), Some(('b', 101)))),
        );
        table.assert_table(&[('a', 'y', 102)]);

        let mut table = HashBasedBiTable::new();
        table.assert_cursors();
        let rs = ('a'..='e').into_iter().cycle();
        let cs = ('x'..='z').into_iter().cycle();
        let vs = (101..=107).into_iter().cycle();
        for ((r, c), v) in iter::zip(iter::zip(rs, cs), vs).take(5 * 3 * 7 * 2) {
            let _ = table.insert(r, c, v);
            table.assert_cursors();
            let _ = table.insert(r, c, v);
            table.assert_cursors();
        }
    }

    #[test]
    fn remove() {
        let expect = [('a', 'x', 100), ('b', 'y', 101)];
        let mut table = HashBasedBiTable::from(expect);
        table.assert_table(&expect);
        assert_eq!(table.remove_row(&'a'), Some(('x', 100)));
        table.assert_table(&[('b', 'y', 101)]);
        assert_eq!(table.remove_row(&'a'), None);
        table.assert_table(&[('b', 'y', 101)]);

        let expect = [('a', 'x', 100), ('b', 'y', 101)];
        let mut table = HashBasedBiTable::from(expect);
        table.assert_table(&expect);
        assert_eq!(table.remove_column(&'y'), Some(('b', 101)));
        table.assert_table(&[('a', 'x', 100)]);
        assert_eq!(table.remove_column(&'y'), None);
        table.assert_table(&[('a', 'x', 100)]);

        let expect = [('a', 'x', 100), ('b', 'y', 101)];
        let mut table = HashBasedBiTable::from(expect);
        table.assert_table(&expect);

        assert_eq!(table.remove(&'a', &'y'), None);
        table.assert_table(&expect);

        assert_eq!(table.remove(&'a', &'x'), Some(100));
        table.assert_table(&[('b', 'y', 101)]);
        assert_eq!(table.remove(&'a', &'x'), None);
        table.assert_table(&[('b', 'y', 101)]);
    }
}
