//! Collection modeled after `Table` in Java Guava library.

use std::borrow::Borrow;
use std::collections::{HashMap, HashSet};
use std::hash::Hash;

#[derive(Clone, Debug)]
pub struct HashBasedTable<R, C, V> {
    table: HashMap<R, HashMap<C, V>>,
    column_capacity: Option<usize>,
}

impl<R, C, V> HashBasedTable<R, C, V> {
    pub fn new() -> Self {
        Self {
            table: HashMap::new(),
            column_capacity: None,
        }
    }

    pub fn with_capacity(row_capacity: usize, column_capacity: usize) -> Self {
        Self {
            table: HashMap::with_capacity(row_capacity),
            column_capacity: Some(column_capacity),
        }
    }
}

fn new_column<C, V>(column_capacity: Option<usize>) -> HashMap<C, V> {
    match column_capacity {
        Some(column_capacity) => HashMap::with_capacity(column_capacity),
        None => HashMap::new(),
    }
}

impl<R, C, V> Default for HashBasedTable<R, C, V> {
    fn default() -> Self {
        Self::new()
    }
}

impl<R, C, V> Extend<(R, C, V)> for HashBasedTable<R, C, V>
where
    R: Eq + Hash,
    C: Eq + Hash,
{
    fn extend<I>(&mut self, iter: I)
    where
        I: IntoIterator<Item = (R, C, V)>,
    {
        for (r, c, v) in iter {
            self.insert(r, c, v);
        }
    }
}

impl<R, C, V, const N: usize> From<[(R, C, V); N]> for HashBasedTable<R, C, V>
where
    R: Eq + Hash,
    C: Eq + Hash,
{
    fn from(arr: [(R, C, V); N]) -> Self {
        Self::from_iter(arr)
    }
}

impl<R, C, V> FromIterator<(R, C, V)> for HashBasedTable<R, C, V>
where
    R: Eq + Hash,
    C: Eq + Hash,
{
    fn from_iter<I>(iter: I) -> Self
    where
        I: IntoIterator<Item = (R, C, V)>,
    {
        let mut table = Self::new();
        table.extend(iter);
        table
    }
}

impl<R, C, V> PartialEq for HashBasedTable<R, C, V>
where
    R: Eq + Hash,
    C: Eq + Hash,
    V: PartialEq,
{
    fn eq(&self, other: &Self) -> bool {
        self.table == other.table
    }
}

impl<R, C, V> Eq for HashBasedTable<R, C, V>
where
    R: Eq + Hash,
    C: Eq + Hash,
    V: Eq,
{
}

impl<R, C, V> HashBasedTable<R, C, V> {
    pub fn row_capacity(&self) -> usize {
        self.table.capacity()
    }

    pub fn is_empty(&self) -> bool {
        self.table.is_empty()
    }

    pub fn num_rows(&self) -> usize {
        self.table.len()
    }

    pub fn num_values(&self) -> usize {
        self.table.values().map(|cs| cs.len()).sum()
    }

    pub fn rows(&self) -> impl Iterator<Item = &R> {
        self.table.keys()
    }

    pub fn values(&self) -> impl Iterator<Item = &V> {
        self.table.values().flat_map(|cs| cs.values())
    }

    pub fn values_mut(&mut self) -> impl Iterator<Item = &mut V> {
        self.table.values_mut().flat_map(|cs| cs.values_mut())
    }

    pub fn iter(&self) -> impl Iterator<Item = (&R, &C, &V)> {
        self.table
            .iter()
            .flat_map(|(r, cs)| cs.iter().map(move |(c, v)| (r, c, v)))
    }

    pub fn iter_mut(&mut self) -> impl Iterator<Item = (&R, &C, &mut V)> {
        self.table
            .iter_mut()
            .flat_map(|(r, cs)| cs.iter_mut().map(move |(c, v)| (r, c, v)))
    }

    pub fn clear(&mut self) {
        self.table.clear();
    }
}

impl<R, C, V> HashBasedTable<R, C, V>
where
    C: Eq + Hash,
{
    pub fn num_columns(&self) -> usize {
        self.column_set().len()
    }

    pub fn columns(&self) -> impl Iterator<Item = &C> {
        self.column_set().into_iter()
    }

    pub fn column_set(&self) -> HashSet<&C> {
        self.table.values().flat_map(|cs| cs.keys()).collect()
    }
}

impl<R, C, V> HashBasedTable<R, C, V>
where
    R: Eq + Hash,
    C: Eq + Hash,
{
    pub fn contains_row<Q>(&self, row: &Q) -> bool
    where
        R: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.table.contains_key(row)
    }

    pub fn contains_column<Q>(&self, column: &Q) -> bool
    where
        C: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.table.values().any(|cs| cs.contains_key(column))
    }

    pub fn contains<RQ, CQ>(&self, row: &RQ, column: &CQ) -> bool
    where
        R: Borrow<RQ>,
        RQ: Eq + Hash + ?Sized,
        C: Borrow<CQ>,
        CQ: Eq + Hash + ?Sized,
    {
        self.table
            .get(row)
            .map(|cs| cs.contains_key(column))
            .unwrap_or(false)
    }

    pub fn iter_row<Q>(&self, row: &Q) -> impl Iterator<Item = (&C, &V)>
    where
        R: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.get_row(row).into_iter().flat_map(|cs| cs.iter())
    }

    pub fn iter_row_mut<Q>(&mut self, row: &Q) -> impl Iterator<Item = (&C, &mut V)>
    where
        R: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.get_row_mut(row)
            .into_iter()
            .flat_map(|cs| cs.iter_mut())
    }

    pub fn iter_column<'a, Q>(&'a self, column: &'a Q) -> impl Iterator<Item = (&'a R, &'a V)>
    where
        C: Borrow<Q>,
        Q: PartialEq<C> + ?Sized,
    {
        self.table.iter().flat_map(move |(r, cs)| {
            cs.iter()
                .filter_map(move |(c, v)| (column == c).then_some((r, v)))
        })
    }

    pub fn iter_column_mut<'a, Q>(
        &'a mut self,
        column: &'a Q,
    ) -> impl Iterator<Item = (&'a R, &'a mut V)>
    where
        C: Borrow<Q>,
        Q: PartialEq<C> + ?Sized,
    {
        self.table.iter_mut().flat_map(move |(r, cs)| {
            cs.iter_mut()
                .filter_map(move |(c, v)| (column == c).then_some((r, v)))
        })
    }

    pub fn get_row<Q>(&self, row: &Q) -> Option<&HashMap<C, V>>
    where
        R: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.table.get(row)
    }

    pub fn get_row_mut<Q>(&mut self, row: &Q) -> Option<&mut HashMap<C, V>>
    where
        R: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.table.get_mut(row)
    }

    pub fn get<RQ, CQ>(&self, row: &RQ, column: &CQ) -> Option<&V>
    where
        R: Borrow<RQ>,
        RQ: Eq + Hash + ?Sized,
        C: Borrow<CQ>,
        CQ: Eq + Hash + ?Sized,
    {
        self.get_row(row).and_then(|cs| cs.get(column))
    }

    pub fn get_mut<RQ, CQ>(&mut self, row: &RQ, column: &CQ) -> Option<&mut V>
    where
        R: Borrow<RQ>,
        RQ: Eq + Hash + ?Sized,
        C: Borrow<CQ>,
        CQ: Eq + Hash + ?Sized,
    {
        self.get_row_mut(row).and_then(|cs| cs.get_mut(column))
    }

    // TODO: Provide an `entry` method equivalent to `HashMap::entry`.  However, implementing
    // `entry` for nested hash maps is challenging.
    pub fn get_or_insert_with<F>(&mut self, row: R, column: C, default: F) -> &mut V
    where
        F: FnOnce() -> V,
    {
        self.table
            .entry(row)
            .or_insert_with(|| new_column(self.column_capacity))
            .entry(column)
            .or_insert_with(default)
    }

    pub fn insert(&mut self, row: R, column: C, value: V) -> Option<V> {
        self.table
            .entry(row)
            .or_insert_with(|| new_column(self.column_capacity))
            .insert(column, value)
    }

    pub fn remove_row<Q>(&mut self, row: &Q) -> Option<HashMap<C, V>>
    where
        R: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        self.table.remove(row)
    }

    pub fn remove_column<Q>(&mut self, column: &Q) -> Option<HashMap<R, V>>
    where
        R: Clone,
        C: Borrow<Q>,
        Q: Eq + Hash + ?Sized,
    {
        let mut rs = HashMap::new();
        for (r, cs) in self.table.iter_mut() {
            if let Some(v) = cs.remove(column) {
                rs.insert(r.clone(), v);
            }
        }
        for row in rs.keys() {
            if self.table.get(row).unwrap().is_empty() {
                self.table.remove(row);
            }
        }
        (!rs.is_empty()).then_some(rs)
    }

    pub fn remove<RQ, CQ>(&mut self, row: &RQ, column: &CQ) -> Option<V>
    where
        R: Borrow<RQ>,
        RQ: Eq + Hash + ?Sized,
        C: Borrow<CQ>,
        CQ: Eq + Hash + ?Sized,
    {
        let cs = self.table.get_mut(row)?;
        let value = cs.remove(column);
        if cs.is_empty() {
            self.table.remove(row);
        }
        value
    }
}

#[cfg(test)]
mod tests {
    use crate::iter::IteratorExt;

    use super::*;

    type Table = HashBasedTable<String, usize, String>;

    fn assert_table<const N: usize>(table: &mut Table, expect: [(&str, usize, &str); N]) {
        let rows: HashSet<_> = expect.iter().map(|(r, _, _)| r.to_string()).collect();
        let columns: HashSet<_> = expect.iter().map(|(_, c, _)| *c).collect();
        let values = expect
            .iter()
            .map(|(_, _, v)| v.to_string())
            .collect_then_sort();
        let items = expect
            .iter()
            .map(|(r, c, v)| (r.to_string(), *c, v.to_string()))
            .collect_then_sort();

        assert_eq!(table.is_empty(), expect.len() == 0);

        assert_eq!(table.num_rows(), rows.len());
        assert_eq!(table.num_columns(), columns.len());
        assert_eq!(table.num_values(), expect.len());

        assert_eq!(table.rows().cloned().collect::<HashSet<_>>(), rows);
        assert_eq!(table.columns().cloned().collect::<HashSet<_>>(), columns);
        assert_eq!(table.values().cloned().collect_then_sort(), values);
        assert_eq!(
            table.values_mut().map(|v| v.clone()).collect_then_sort(),
            values,
        );

        assert_eq!(
            table
                .iter()
                .map(|(r, c, v)| (r.clone(), *c, v.clone()))
                .collect_then_sort(),
            items,
        );
        assert_eq!(
            table
                .iter_mut()
                .map(|(r, c, v)| (r.clone(), *c, v.clone()))
                .collect_then_sort(),
            items,
        );

        for (row, column, value) in &expect {
            let row = *row;
            let mut value = value.to_string();
            assert_eq!(table.contains_row(row), true);
            assert_eq!(table.contains_column(column), true);
            assert_eq!(table.contains(row, column), true);
            assert_eq!(table.get(row, column), Some(&value));
            assert_eq!(table.get_mut(row, column), Some(&mut value));
        }

        assert_eq!(table, &Table::from_iter(items.into_iter()));

        for cs in table.table.values() {
            assert_eq!(cs.is_empty(), false);
        }
    }

    #[test]
    fn from() {
        let mut table = Table::from([
            ("a".to_string(), 1, "foo".to_string()),
            ("a".to_string(), 1, "duplicated".to_string()),
            ("a".to_string(), 2, "bar".to_string()),
            ("b".to_string(), 1, "spam".to_string()),
            ("b".to_string(), 3, "egg".to_string()),
        ]);
        assert_eq!(
            table.table,
            HashMap::from([
                (
                    "a".to_string(),
                    HashMap::from([(1, "duplicated".to_string()), (2, "bar".to_string())])
                ),
                (
                    "b".to_string(),
                    HashMap::from([(1, "spam".to_string()), (3, "egg".to_string())])
                ),
            ]),
        );
        assert_table(
            &mut table,
            [
                ("a", 1, "duplicated"),
                ("a", 2, "bar"),
                ("b", 1, "spam"),
                ("b", 3, "egg"),
            ],
        );
    }

    #[test]
    fn eq() {
        assert_eq!(Table::new(), Table::with_capacity(3, 4));

        let mut t1 = Table::new();
        t1.insert("a".to_string(), 1, "foo".to_string());
        let mut t2 = Table::with_capacity(3, 4);
        t2.insert("a".to_string(), 1, "foo".to_string());
        assert_eq!(t1, t2);

        let mut t1 = Table::new();
        t1.insert("a".to_string(), 1, "foo".to_string());
        let mut t2 = Table::with_capacity(3, 4);
        t2.insert("a".to_string(), 1, "bar".to_string());
        assert_ne!(t1, t2);
    }

    #[test]
    fn clear() {
        let mut table = Table::from([
            ("a".to_string(), 1, "foo".to_string()),
            ("a".to_string(), 2, "bar".to_string()),
            ("b".to_string(), 1, "spam".to_string()),
            ("b".to_string(), 3, "egg".to_string()),
        ]);
        assert_eq!(table.is_empty(), false);

        table.clear();
        assert_table(&mut table, []);
    }

    #[test]
    fn not_contains() {
        let table = Table::from([
            ("a".to_string(), 1, "foo".to_string()),
            ("b".to_string(), 2, "bar".to_string()),
        ]);
        assert_eq!(table.contains_row("c"), false);
        assert_eq!(table.contains_column(&3), false);
        assert_eq!(table.contains("a", &2), false);
        assert_eq!(table.contains("b", &1), false);
    }

    #[test]
    fn iter() {
        let mut table = Table::from([
            ("a".to_string(), 1, "foo".to_string()),
            ("a".to_string(), 2, "bar".to_string()),
            ("b".to_string(), 1, "spam".to_string()),
            ("b".to_string(), 3, "egg".to_string()),
        ]);

        assert_eq!(
            table.iter_row("a").collect_then_sort(),
            vec![(&1, &"foo".to_string()), (&2, &"bar".to_string())],
        );
        assert_eq!(
            table.iter_row_mut("a").collect_then_sort(),
            vec![(&1, &mut "foo".to_string()), (&2, &mut "bar".to_string())],
        );
        assert_eq!(
            table.iter_row("b").collect_then_sort(),
            vec![(&1, &"spam".to_string()), (&3, &"egg".to_string())],
        );
        assert_eq!(table.iter_row("c").collect_then_sort(), Vec::new());

        assert_eq!(
            table.iter_column(&1).collect_then_sort(),
            vec![
                (&"a".to_string(), &"foo".to_string()),
                (&"b".to_string(), &"spam".to_string()),
            ],
        );
        assert_eq!(
            table.iter_column_mut(&1).collect_then_sort(),
            vec![
                (&"a".to_string(), &mut "foo".to_string()),
                (&"b".to_string(), &mut "spam".to_string()),
            ],
        );
        assert_eq!(
            table.iter_column(&2).collect_then_sort(),
            vec![(&"a".to_string(), &"bar".to_string())],
        );
        assert_eq!(
            table.iter_column(&3).collect_then_sort(),
            vec![(&"b".to_string(), &"egg".to_string())],
        );
        assert_eq!(table.iter_column(&4).collect_then_sort(), Vec::new());
    }

    #[test]
    fn get_or_insert_with() {
        let mut table = Table::new();

        assert_eq!(
            table.get_or_insert_with("a".to_string(), 1, || "foo".to_string()),
            "foo",
        );
        assert_table(&mut table, [("a", 1, "foo")]);

        assert_eq!(
            table.get_or_insert_with("a".to_string(), 1, || "bar".to_string()),
            "foo",
        );
        assert_table(&mut table, [("a", 1, "foo")]);
    }

    #[test]
    fn insert() {
        let mut table = Table::new();

        assert_eq!(table.insert("a".to_string(), 1, "foo".to_string()), None);
        assert_table(&mut table, [("a", 1, "foo")]);

        assert_eq!(
            table.insert("a".to_string(), 1, "bar".to_string()),
            Some("foo".to_string()),
        );
        assert_table(&mut table, [("a", 1, "bar")]);
    }

    #[test]
    fn remove() {
        let testdata = Table::from([
            ("a".to_string(), 1, "foo".to_string()),
            ("a".to_string(), 2, "bar".to_string()),
            ("b".to_string(), 1, "spam".to_string()),
            ("b".to_string(), 3, "egg".to_string()),
        ]);

        let mut table = testdata.clone();

        assert_eq!(
            table.remove_row("a"),
            Some(HashMap::from([
                (1, "foo".to_string()),
                (2, "bar".to_string()),
            ])),
        );
        assert_table(&mut table, [("b", 1, "spam"), ("b", 3, "egg")]);

        assert_eq!(table.remove_row("a"), None);
        assert_table(&mut table, [("b", 1, "spam"), ("b", 3, "egg")]);

        let mut table = testdata.clone();

        assert_eq!(
            table.remove_column(&1),
            Some(HashMap::from([
                ("a".to_string(), "foo".to_string()),
                ("b".to_string(), "spam".to_string()),
            ])),
        );
        assert_table(&mut table, [("a", 2, "bar"), ("b", 3, "egg")]);

        assert_eq!(table.remove_column(&1), None);
        assert_table(&mut table, [("a", 2, "bar"), ("b", 3, "egg")]);

        assert_eq!(
            table.remove_column(&2),
            Some(HashMap::from([("a".to_string(), "bar".to_string())])),
        );
        assert_table(&mut table, [("b", 3, "egg")]);

        assert_eq!(
            table.remove_column(&3),
            Some(HashMap::from([("b".to_string(), "egg".to_string())])),
        );
        assert_table(&mut table, []);

        let mut table = testdata.clone();

        assert_eq!(table.remove("a", &1), Some("foo".to_string()));
        assert_table(
            &mut table,
            [("a", 2, "bar"), ("b", 1, "spam"), ("b", 3, "egg")],
        );

        assert_eq!(table.remove("a", &1), None);
        assert_table(
            &mut table,
            [("a", 2, "bar"), ("b", 1, "spam"), ("b", 3, "egg")],
        );

        assert_eq!(table.remove("a", &2), Some("bar".to_string()));
        assert_table(&mut table, [("b", 1, "spam"), ("b", 3, "egg")]);
    }
}
