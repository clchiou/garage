use std::cmp::Ordering;

/// Extends the `std::iter::Iterator` trait.
pub trait IteratorExt: Iterator {
    fn collect_then_sort(self) -> Vec<Self::Item>
    where
        Self: Sized,
        Self::Item: Ord,
    {
        let mut items: Vec<_> = self.collect();
        items.sort();
        items
    }

    fn collect_then_sort_by<F>(self, compare: F) -> Vec<Self::Item>
    where
        Self: Sized,
        F: FnMut(&Self::Item, &Self::Item) -> Ordering,
    {
        let mut items: Vec<_> = self.collect();
        items.sort_by(compare);
        items
    }

    fn collect_then_sort_by_key<K, F>(self, to_key: F) -> Vec<Self::Item>
    where
        Self: Sized,
        F: FnMut(&Self::Item) -> K,
        K: Ord,
    {
        let mut items: Vec<_> = self.collect();
        items.sort_by_key(to_key);
        items
    }
}

impl<T> IteratorExt for T where T: Iterator {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn collect_then_sort() {
        assert_eq!([3, 1, 2].into_iter().collect_then_sort(), vec![1, 2, 3]);
        assert_eq!(
            [3, 1, 2].into_iter().collect_then_sort_by(|x, y| x.cmp(y)),
            vec![1, 2, 3],
        );
        assert_eq!(
            [3, 1, 2].into_iter().collect_then_sort_by_key(|x| *x),
            vec![1, 2, 3],
        );
    }
}
