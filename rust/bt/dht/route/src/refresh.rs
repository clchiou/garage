use std::time::Duration;

use tokio::time::Instant;

// A bucket should be refreshed after this period without change.
const REFRESH_TIMEOUT: Duration = Duration::from_mins(15);

/// Queue of `(deadline, bucket_index)` pairs, sorted in ascending order by `deadline`.
// TODO: This is not very efficient, but it should be sufficient for now.
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct RefreshQueue(Vec<(Instant, usize)>);

impl RefreshQueue {
    pub(crate) fn new() -> Self {
        Self(Vec::new())
    }

    fn partition_point(&self, deadline: Instant) -> usize {
        self.0.partition_point(|(d, _)| *d <= deadline)
    }

    fn position(&self, bucket_index: usize) -> Option<usize> {
        self.0.iter().position(|(_, i)| *i == bucket_index)
    }

    fn insert_sorted(&mut self, pair: (Instant, usize)) {
        self.0.insert(self.partition_point(pair.0), pair)
    }

    pub(crate) fn insert(&mut self, bucket_index: usize, when: Instant) {
        let deadline = when + REFRESH_TIMEOUT;

        if let Some(i) = self.position(bucket_index) {
            if self.0[i].0 >= deadline {
                return;
            }

            self.0.remove(i);
        }

        self.insert_sorted((deadline, bucket_index));
    }

    pub(crate) fn peek(&self) -> Option<&(Instant, usize)> {
        self.0.first()
    }

    pub(crate) fn next(&mut self) -> Option<(Instant, usize)> {
        (!self.0.is_empty()).then(|| self.0.remove(0))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn insert() {
        let t0 = Instant::now();
        let t1 = t0 + Duration::SECOND;
        let t2 = t1 + Duration::SECOND;

        let tt0 = t0 + REFRESH_TIMEOUT;
        let tt1 = t1 + REFRESH_TIMEOUT;
        let tt2 = t2 + REFRESH_TIMEOUT;

        let mut refresh = RefreshQueue::new();
        assert_eq!(refresh.0, []);

        refresh.insert(100, t2);
        assert_eq!(refresh.0, [(tt2, 100)]);
        refresh.insert(100, t1);
        assert_eq!(refresh.0, [(tt2, 100)]);

        refresh.insert(99, t0);
        assert_eq!(refresh.0, [(tt0, 99), (tt2, 100)]);

        refresh.insert(98, t1);
        assert_eq!(refresh.0, [(tt0, 99), (tt1, 98), (tt2, 100)]);
        refresh.insert(98, t2);
        assert_eq!(refresh.0, [(tt0, 99), (tt2, 100), (tt2, 98)]);
    }

    #[test]
    fn peek() {
        let t0 = Instant::now();
        let t1 = t0 + Duration::SECOND;

        let tt0 = t0 + REFRESH_TIMEOUT;
        let tt1 = t1 + REFRESH_TIMEOUT;

        let mut refresh = RefreshQueue::new();
        assert_eq!(refresh.0, []);

        assert_eq!(refresh.peek(), None);
        assert_eq!(refresh.0, []);

        refresh.insert(0, t0);
        refresh.insert(1, t1);
        assert_eq!(refresh.0, [(tt0, 0), (tt1, 1)]);

        assert_eq!(refresh.peek(), Some(&(tt0, 0)));
        assert_eq!(refresh.0, [(tt0, 0), (tt1, 1)]);
    }

    #[test]
    fn next() {
        let t0 = Instant::now();
        let t1 = t0 + Duration::SECOND;

        let tt0 = t0 + REFRESH_TIMEOUT;
        let tt1 = t1 + REFRESH_TIMEOUT;

        let mut refresh = RefreshQueue::new();
        assert_eq!(refresh.0, []);

        assert_eq!(refresh.next(), None);
        assert_eq!(refresh.0, []);

        refresh.insert(0, t0);
        refresh.insert(1, t1);
        assert_eq!(refresh.0, [(tt0, 0), (tt1, 1)]);

        assert_eq!(refresh.next(), Some((tt0, 0)));
        assert_eq!(refresh.0, [(tt1, 1)]);
    }
}
