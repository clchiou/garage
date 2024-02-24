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

pub fn product<'a, XS, YS, X, Y>(xs: XS, ys: YS) -> impl Iterator<Item = (&'a X, &'a Y)>
where
    XS: IntoIterator<Item = &'a X>,
    YS: IntoIterator<Item = &'a Y>,
    <YS as IntoIterator>::IntoIter: Clone,
    X: 'a,
    Y: 'a,
{
    let xs = xs.into_iter();
    let ys = ys.into_iter();
    xs.flat_map(move |x| ys.clone().map(move |y| (x, y)))
}

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

    #[test]
    fn test_product() {
        fn test<const N: usize>(xs: &[usize], ys: &[usize], expect: [(usize, usize); N]) {
            assert_eq!(
                product(xs, ys).map(|(x, y)| (*x, *y)).collect::<Vec<_>>(),
                expect,
            );
        }

        test(&[], &[], []);
        test(&[1], &[], []);
        test(&[], &[10], []);
        test(&[1], &[10], [(1, 10)]);
        test(&[1, 2], &[10], [(1, 10), (2, 10)]);
        test(&[1], &[10, 20], [(1, 10), (1, 20)]);
        test(&[1, 2], &[10, 20], [(1, 10), (1, 20), (2, 10), (2, 20)]);
    }
}
