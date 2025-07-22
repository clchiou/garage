use std::time::Duration;

use tokio::time::Instant;

use g1_base::collections::Array;

use bt_base::NodeId;
use bt_dht_proto::NodeInfo;

use crate::K;

// A good node becomes stale after this period of inactivity.
const INACTIVITY_TIMEOUT: Duration = Duration::from_mins(15);

// A node becomes bad after this many query failures in a row.
const FAILURE_THRESHOLD: usize = 3;

// Sorted in ascending order by `last_ok`.
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct Bucket(Array<BucketItem, K>);

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct BucketItem {
    info: NodeInfo,
    // Implements the "last activity" timer.
    last_ok: Option<Instant>,
    // Removes the node from the bucket automatically after it fails consecutively.
    num_errs: usize,
}

impl Bucket {
    pub(crate) fn new() -> Self {
        Self(Array::new())
    }

    /// Splits `self` and returns the nodes that are closer to the `self_id` bit.
    pub(crate) fn split_off(&mut self, bit_index: usize, bit: bool) -> Self {
        let mut closer = Self::new();
        let mut i = 0;
        while i < self.0.len() {
            if self.0[i].info.id.bits()[bit_index] == bit {
                closer.0.push(self.0.remove(i));
            } else {
                i += 1;
            }
        }
        closer
    }

    /// Returns the first index of the greater-than item.
    fn partition_point(&self, last_ok: Option<Instant>) -> usize {
        self.0.partition_point(|item| item.last_ok <= last_ok)
    }

    fn position(&self, id: &NodeId) -> Option<usize> {
        self.0.iter().position(|item| &item.info.id == id)
    }

    fn insert_sorted(&mut self, item: BucketItem) -> Result<(), BucketItem> {
        self.0.try_insert(self.partition_point(item.last_ok), item)
    }

    /// Returns node info sorted in descending order by `last_ok`.
    pub(crate) fn iter(&self) -> impl Iterator<Item = NodeInfo> {
        self.0.iter().rev().map(|item| item.info.clone())
    }

    /// Returns stale node info sorted in ascending order by `last_ok`.
    pub(crate) fn stale(&self, now: Instant) -> impl Iterator<Item = NodeInfo> {
        self.0[..self.partition_point(Some(now - INACTIVITY_TIMEOUT))]
            .iter()
            .map(|item| item.info.clone())
    }

    /// Inserts or updates the item.
    ///
    /// It returns `Ok` as long as the bucket containing the item, regardless of whether it was
    /// updated or inserted by the call.
    pub(crate) fn insert(&mut self, item: BucketItem) -> Result<(), BucketItem> {
        if let Some(i) = self.position(&item.info.id) {
            if self.0[i].last_ok >= item.last_ok {
                return Ok(());
            }

            self.0.remove(i);
        }

        self.insert_sorted(item)?;

        Ok(())
    }

    /// Updates an item's `last_ok` timer.
    ///
    /// It returns true as long as the bucket containing the item, regardless of whether it was
    /// updated by the call.
    #[must_use]
    pub(crate) fn update_ok(&mut self, info: NodeInfo, when: Instant) -> bool {
        let Some(i) = self.position(&info.id) else {
            return false;
        };

        let last_ok = Some(when);
        if self.0[i].last_ok >= last_ok {
            return true;
        }

        // Create a new item (which also clears `num_errs`) in case the node changes its endpoint.
        self.0.remove(i);
        self.insert_sorted(BucketItem::new(info, last_ok))
            .expect("insert_sorted");

        true
    }

    /// Updates an item's `num_errs` counter, and removes a failed item automatically.
    pub(crate) fn update_err(&mut self, id: NodeId) {
        let Some(i) = self.position(&id) else {
            return;
        };

        self.0[i].num_errs += 1;
        if self.0[i].num_errs >= FAILURE_THRESHOLD {
            self.0.remove(i);
        }
    }

    pub(crate) fn remove(&mut self, id: NodeId) -> Option<BucketItem> {
        self.position(&id).map(|i| self.0.remove(i))
    }
}

impl BucketItem {
    pub(crate) fn new(info: NodeInfo, last_ok: Option<Instant>) -> Self {
        Self {
            info,
            last_ok,
            num_errs: 0,
        }
    }

    pub(crate) fn id(&self) -> &NodeId {
        &self.info.id
    }
}

#[cfg(test)]
pub(crate) mod testing {
    use tokio::time::Instant;

    use g1_base::collections::Array;

    use bt_dht_proto::NodeInfo;

    use super::{Bucket, BucketItem};

    impl Bucket {
        pub(crate) fn assert_eq(&self, expect: &[(&NodeInfo, Option<Instant>, usize)]) {
            assert_eq!(
                self.0,
                Array::from_iter(expect.iter().map(|&(info, last_ok, num_errs)| BucketItem {
                    info: info.clone(),
                    last_ok,
                    num_errs,
                }),),
            );
        }

        pub(crate) fn assert_infos(&self, expect: &[&NodeInfo]) {
            assert_eq!(
                self.0.iter().map(|item| &item.info).collect::<Vec<_>>(),
                expect,
            );
        }
    }

    pub(crate) fn bi(info: &NodeInfo, last_ok: Option<Instant>) -> BucketItem {
        BucketItem::new(info.clone(), last_ok)
    }
}

#[cfg(test)]
mod tests {
    use bt_base::node_id::NodeIdBitSlice;

    use crate::testing::ni;

    use super::testing::bi;
    use super::*;

    #[test]
    fn split_off() {
        fn make(i: usize) -> NodeInfo {
            let mut id = [0; 20];
            NodeIdBitSlice::from_slice_mut(&mut id).set(i, true);
            ni(id, 8000)
        }

        let zero = make(0);
        let one = make(1);
        let two = make(2);
        let three = make(3);

        let mut testdata = Bucket::new();
        assert_eq!(testdata.insert_sorted(bi(&zero, None)), Ok(()));
        assert_eq!(testdata.insert_sorted(bi(&one, None)), Ok(()));
        assert_eq!(testdata.insert_sorted(bi(&two, None)), Ok(()));
        assert_eq!(testdata.insert_sorted(bi(&three, None)), Ok(()));
        testdata.assert_infos(&[&zero, &one, &two, &three]);

        {
            let mut bucket = testdata.clone();
            let closer = bucket.split_off(0, true);
            bucket.assert_infos(&[&one, &two, &three]);
            closer.assert_infos(&[&zero]);

            let mut bucket = testdata.clone();
            let closer = bucket.split_off(0, false);
            bucket.assert_infos(&[&zero]);
            closer.assert_infos(&[&one, &two, &three]);
        }

        {
            let mut bucket = testdata.clone();
            let closer = bucket.split_off(1, true);
            bucket.assert_infos(&[&zero, &two, &three]);
            closer.assert_infos(&[&one]);

            let mut bucket = testdata.clone();
            let closer = bucket.split_off(1, false);
            bucket.assert_infos(&[&one]);
            closer.assert_infos(&[&zero, &two, &three]);
        }

        {
            let mut bucket = testdata.clone();
            let closer = bucket.split_off(4, true);
            bucket.assert_infos(&[&zero, &one, &two, &three]);
            closer.assert_infos(&[]);

            let mut bucket = testdata.clone();
            let closer = bucket.split_off(4, false);
            bucket.assert_infos(&[]);
            closer.assert_infos(&[&zero, &one, &two, &three]);
        }
    }

    #[test]
    fn partition_point() {
        let zero = ni([0; 20], 8000);

        let t0 = Instant::now();

        {
            let bucket = Bucket::new();
            assert_eq!(bucket.partition_point(None), 0);
            assert_eq!(bucket.partition_point(Some(t0)), 0);
        }

        {
            let mut bucket = Bucket::new();
            for i in 0..3 {
                assert_eq!(bucket.insert_sorted(bi(&zero, None)), Ok(()));
                assert_eq!(bucket.partition_point(None), i + 1);
                assert_eq!(bucket.partition_point(Some(t0)), i + 1);
            }
        }

        {
            let mut bucket = Bucket::new();
            for i in 0..3 {
                assert_eq!(bucket.insert_sorted(bi(&zero, Some(t0))), Ok(()));
                assert_eq!(bucket.partition_point(None), 0);
                assert_eq!(bucket.partition_point(Some(t0)), i + 1);
            }
        }

        {
            let mut bucket = Bucket::new();
            for i in 0..3 {
                let t = t0 + Duration::from_secs(i);
                assert_eq!(bucket.insert_sorted(bi(&zero, Some(t))), Ok(()));
            }

            assert_eq!(bucket.partition_point(None), 0);
            for i in 0..3 {
                let t = t0 + Duration::from_secs(i);
                assert_eq!(bucket.partition_point(Some(t)), (i + 1).try_into().unwrap());
            }
            for i in 3..6 {
                let t = t0 + Duration::from_secs(i);
                assert_eq!(bucket.partition_point(Some(t)), 3);
            }
        }
    }

    #[test]
    fn insert_sorted() {
        let zero = ni([0; 20], 8000);
        let one = ni([1; 20], 8000);
        let two = ni([2; 20], 8000);
        let three = ni([3; 20], 8000);

        let t0 = Instant::now();
        let t1 = t0 + Duration::SECOND;
        let t2 = t1 + Duration::SECOND;

        {
            let mut bucket = Bucket::new();
            bucket.assert_infos(&[]);

            assert_eq!(bucket.insert_sorted(bi(&zero, Some(t1))), Ok(()));
            bucket.assert_infos(&[&zero]);

            assert_eq!(bucket.insert_sorted(bi(&one, Some(t0))), Ok(()));
            bucket.assert_infos(&[&one, &zero]);

            assert_eq!(bucket.insert_sorted(bi(&two, None)), Ok(()));
            bucket.assert_infos(&[&two, &one, &zero]);

            assert_eq!(bucket.insert_sorted(bi(&three, Some(t2))), Ok(()));
            bucket.assert_infos(&[&two, &one, &zero, &three]);
        }

        {
            let mut bucket = Bucket::new();
            bucket.assert_infos(&[]);

            assert_eq!(bucket.insert_sorted(bi(&one, None)), Ok(()));
            bucket.assert_infos(&[&one]);

            assert_eq!(bucket.insert_sorted(bi(&zero, None)), Ok(()));
            bucket.assert_infos(&[&one, &zero]);

            assert_eq!(bucket.insert_sorted(bi(&two, None)), Ok(()));
            bucket.assert_infos(&[&one, &zero, &two]);
        }

        {
            let mut bucket = Bucket::new();
            bucket.assert_infos(&[]);

            assert_eq!(bucket.insert_sorted(bi(&one, Some(t0))), Ok(()));
            bucket.assert_infos(&[&one]);

            assert_eq!(bucket.insert_sorted(bi(&zero, Some(t0))), Ok(()));
            bucket.assert_infos(&[&one, &zero]);

            assert_eq!(bucket.insert_sorted(bi(&two, Some(t0))), Ok(()));
            bucket.assert_infos(&[&one, &zero, &two]);
        }

        {
            let mut bucket = Bucket::new();
            bucket.assert_infos(&[]);
            for len in 1..=K {
                assert_eq!(bucket.insert_sorted(bi(&zero, None)), Ok(()));
                assert_eq!(bucket.0.len(), len);
            }

            let item = bi(&zero, None);
            assert_eq!(bucket.insert_sorted(item.clone()), Err(item));

            let item = bi(&one, Some(t0));
            assert_eq!(bucket.insert_sorted(item.clone()), Err(item));
        }
    }

    #[test]
    fn iter() {
        let zero = ni([0; 20], 8000);
        let one = ni([1; 20], 8001);
        let two = ni([2; 20], 8002);

        let t0 = Instant::now();
        let t1 = t0 + Duration::SECOND;

        let mut bucket = Bucket::new();
        assert_eq!(bucket.insert_sorted(bi(&zero, None)), Ok(()));
        assert_eq!(bucket.insert_sorted(bi(&one, Some(t0))), Ok(()));
        assert_eq!(bucket.insert_sorted(bi(&two, Some(t1))), Ok(()));
        bucket.assert_infos(&[&zero, &one, &two]);

        assert_eq!(bucket.iter().collect::<Vec<_>>(), &[two, one, zero]);
    }

    #[test]
    fn stale() {
        let none = ni([0xff; 20], 8000);
        let zero = ni([0; 20], 8000);
        let one = ni([1; 20], 8000);
        let two = ni([2; 20], 8000);
        let three = ni([3; 20], 8000);

        let t3 = Instant::now();
        let t4 = t3 + Duration::SECOND;

        let t2 = t3 - INACTIVITY_TIMEOUT + Duration::SECOND;
        let t1 = t3 - INACTIVITY_TIMEOUT;
        let t0 = t3 - INACTIVITY_TIMEOUT - Duration::SECOND;

        let mut bucket = Bucket::new();
        assert_eq!(bucket.insert_sorted(bi(&none, None)), Ok(()));
        assert_eq!(bucket.insert_sorted(bi(&zero, Some(t0))), Ok(()));
        assert_eq!(bucket.insert_sorted(bi(&one, Some(t1))), Ok(()));
        assert_eq!(bucket.insert_sorted(bi(&two, Some(t2))), Ok(()));
        assert_eq!(bucket.insert_sorted(bi(&three, Some(t3))), Ok(()));
        bucket.assert_infos(&[&none, &zero, &one, &two, &three]);

        for t in [t0, t1, t2] {
            assert_eq!(bucket.stale(t).collect::<Vec<_>>(), &[none.clone()]);
        }
        assert_eq!(
            bucket.stale(t3).collect::<Vec<_>>(),
            &[none.clone(), zero.clone(), one.clone()],
        );
        assert_eq!(
            bucket.stale(t4).collect::<Vec<_>>(),
            &[none.clone(), zero.clone(), one.clone(), two.clone()],
        );
    }

    #[test]
    fn insert() {
        let zero = ni([0; 20], 8000);
        let change_port = ni([0; 20], 8001);

        let t0 = Instant::now();
        let t1 = t0 + Duration::SECOND;

        {
            let mut bucket = Bucket::new();
            bucket.assert_eq(&[]);

            assert_eq!(bucket.insert(bi(&zero, None)), Ok(()));
            bucket.assert_eq(&[(&zero, None, 0)]);

            assert_eq!(bucket.insert(bi(&zero, None)), Ok(()));
            bucket.assert_eq(&[(&zero, None, 0)]);
        }

        {
            let mut bucket = Bucket::new();
            bucket.assert_eq(&[]);

            assert_eq!(bucket.insert(bi(&zero, None)), Ok(()));
            bucket.assert_eq(&[(&zero, None, 0)]);

            assert_eq!(bucket.insert(bi(&zero, Some(t0))), Ok(()));
            bucket.assert_eq(&[(&zero, Some(t0), 0)]);
        }

        {
            let mut bucket = Bucket::new();
            bucket.assert_eq(&[]);

            assert_eq!(bucket.insert(bi(&zero, Some(t0))), Ok(()));
            bucket.assert_eq(&[(&zero, Some(t0), 0)]);

            assert_eq!(bucket.insert(bi(&zero, None)), Ok(()));
            bucket.assert_eq(&[(&zero, Some(t0), 0)]);
        }

        {
            let mut bucket = Bucket::new();
            bucket.assert_eq(&[]);

            assert_eq!(bucket.insert(bi(&zero, Some(t0))), Ok(()));
            bucket.assert_eq(&[(&zero, Some(t0), 0)]);

            assert_eq!(bucket.insert(bi(&zero, Some(t1))), Ok(()));
            bucket.assert_eq(&[(&zero, Some(t1), 0)]);
        }

        {
            let mut bucket = Bucket::new();
            bucket.assert_eq(&[]);

            let mut item = bi(&zero, Some(t0));
            item.num_errs = 1;
            assert_eq!(bucket.insert(item), Ok(()));
            bucket.assert_eq(&[(&zero, Some(t0), 1)]);

            assert_eq!(bucket.insert(bi(&zero, Some(t0))), Ok(()));
            bucket.assert_eq(&[(&zero, Some(t0), 1)]);
        }

        {
            let mut bucket = Bucket::new();
            bucket.assert_eq(&[]);

            assert_eq!(bucket.insert(bi(&zero, None)), Ok(()));
            bucket.assert_eq(&[(&zero, None, 0)]);

            assert_eq!(bucket.insert(bi(&change_port, Some(t0))), Ok(()));
            bucket.assert_eq(&[(&change_port, Some(t0), 0)]);
        }

        {
            let mut bucket = Bucket::new();
            for _ in 0..3 {
                for i in 0..K {
                    let i = u8::try_from(i).unwrap();
                    let i = ni([i; 20], 8000);
                    assert_eq!(bucket.insert(bi(&i, None)), Ok(()));
                }
            }

            let item = bi(&ni([0xff; 20], 8000), None);
            assert_eq!(bucket.insert(item.clone()), Err(item));
        }
    }

    #[test]
    fn update_ok() {
        let zero = ni([0; 20], 8000);
        let change_port = ni([0; 20], 8001);

        let t0 = Instant::now();
        let t1 = t0 + Duration::SECOND;

        let new_item = |last_ok: Option<Instant>, num_errs: usize| {
            let mut item = bi(&zero, last_ok);
            item.num_errs = num_errs;
            item
        };

        {
            let mut bucket = Bucket::new();
            bucket.assert_eq(&[]);

            assert_eq!(bucket.update_ok(zero.clone(), t0), false);
            bucket.assert_eq(&[]);
        }

        {
            let mut bucket = Bucket::new();
            assert_eq!(bucket.insert_sorted(new_item(None, 1)), Ok(()));
            bucket.assert_eq(&[(&zero, None, 1)]);

            assert_eq!(bucket.update_ok(zero.clone(), t0), true);
            bucket.assert_eq(&[(&zero, Some(t0), 0)]);
        }

        {
            let mut bucket = Bucket::new();
            assert_eq!(bucket.insert_sorted(new_item(Some(t0), 1)), Ok(()));
            bucket.assert_eq(&[(&zero, Some(t0), 1)]);

            assert_eq!(bucket.update_ok(zero.clone(), t1), true);
            bucket.assert_eq(&[(&zero, Some(t1), 0)]);
        }

        {
            let mut bucket = Bucket::new();
            assert_eq!(bucket.insert_sorted(new_item(Some(t0), 1)), Ok(()));
            bucket.assert_eq(&[(&zero, Some(t0), 1)]);

            assert_eq!(bucket.update_ok(zero.clone(), t0), true);
            bucket.assert_eq(&[(&zero, Some(t0), 1)]);
        }

        {
            let mut bucket = Bucket::new();
            assert_eq!(bucket.insert_sorted(new_item(None, 1)), Ok(()));
            bucket.assert_eq(&[(&zero, None, 1)]);

            assert_eq!(bucket.update_ok(change_port.clone(), t0), true);
            bucket.assert_eq(&[(&change_port, Some(t0), 0)]);
        }
    }

    #[test]
    fn update_err() {
        let zero = ni([0; 20], 8000);
        let one = ni([1; 20], 8000);

        let mut bucket = Bucket::new();
        assert_eq!(bucket.insert_sorted(bi(&zero, None)), Ok(()));
        bucket.assert_eq(&[(&zero, None, 0)]);

        for _ in 0..3 {
            bucket.update_err(one.id.clone());
            bucket.assert_eq(&[(&zero, None, 0)]);
        }

        for n in 1..FAILURE_THRESHOLD {
            bucket.update_err(zero.id.clone());
            bucket.assert_eq(&[(&zero, None, n)]);
        }

        bucket.update_err(zero.id.clone());
        bucket.assert_eq(&[]);
    }
}
