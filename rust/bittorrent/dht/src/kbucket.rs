use std::cmp;
use std::time::Instant;

use crate::NodeContactInfo;

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct KBucket {
    // Sorted by `last_seen` ascending.
    // TODO: This does not feel very efficient.  Can we improve it?
    items: Vec<KBucketItem>,
    pub(crate) max_bucket_size: usize,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct KBucketItem {
    pub(crate) contact_info: NodeContactInfo,
    last_seen: Instant,
}

impl KBucket {
    pub(crate) fn new(max_bucket_size: usize) -> Self {
        Self {
            items: Vec::new(),
            max_bucket_size,
        }
    }

    pub(crate) fn iter(&self) -> impl Iterator<Item = &NodeContactInfo> {
        self.items.iter().map(|item| &item.contact_info)
    }

    pub(crate) fn recently_seen(&self) -> Option<Instant> {
        self.items.last().map(|item| item.last_seen)
    }

    pub(crate) fn split(&mut self, bit_index: usize) -> (Self, Self) {
        let mut left = Self::new(self.max_bucket_size);
        let mut right = Self::new(self.max_bucket_size);
        for item in self.items.drain(..) {
            if item.contact_info.id.bits()[bit_index] {
                left.items.push(item);
            } else {
                right.items.push(item);
            }
        }
        (left, right)
    }

    fn find_by_id(&self, contact_info: &NodeContactInfo) -> Option<usize> {
        let (i, _) = self
            .items
            .iter()
            .enumerate()
            .find(|(_, item)| item.contact_info.id == contact_info.id)?;
        Some(i)
    }

    pub(crate) fn insert(&mut self, mut candidate: KBucketItem) -> Result<(), KBucketItem> {
        if self.items.len() >= self.max_bucket_size {
            return Err(candidate);
        }

        if let Some(i) = self.find_by_id(&candidate.contact_info) {
            let incumbent = self.items.remove(i);
            if incumbent.contact_info != candidate.contact_info {
                // We are observing the same node id at different addresses.  This is less likely
                // to be due to a node id conflict and more likely to be because this node has
                // changed its address.
                tracing::warn!(
                    ?incumbent.contact_info,
                    ?candidate.contact_info,
                    "node address change",
                );
            }
            // Call `cmp::max` because it is possible that the candidate is created before the
            // incumbent gets updated and inserted afterward, potentially leading to
            // `incumbent.last_seen` being newer than `candidate.last_seen`.
            candidate.last_seen = cmp::max(incumbent.last_seen, candidate.last_seen);
        }

        let i = match self
            .items
            .binary_search_by_key(&candidate.last_seen, |item| item.last_seen)
        {
            Ok(i) => i,
            Err(i) => i,
        };
        self.items.insert(i, candidate);
        Ok(())
    }

    /// Like `insert`, but removes the least recently seen items to ensure that there is space in
    /// the bucket.
    pub(crate) fn must_insert(&mut self, candidate: KBucketItem) {
        while self.items.len() >= self.max_bucket_size {
            self.items.remove(0);
        }
        assert!(self.insert(candidate).is_ok());
    }

    pub(crate) fn remove(&mut self, contact_info: &NodeContactInfo) -> Option<KBucketItem> {
        Some(self.items.remove(self.find_by_id(contact_info)?))
    }
}

impl KBucketItem {
    pub(crate) fn new(contact_info: NodeContactInfo) -> Self {
        Self {
            contact_info,
            last_seen: Instant::now(),
        }
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl KBucket {
        pub(crate) fn new_mock(
            max_bucket_size: usize,
            items: impl Iterator<Item = KBucketItem>,
        ) -> Self {
            Self {
                items: items.collect(),
                max_bucket_size,
            }
        }

        pub(crate) fn assert_items(&self, expect: &[&KBucketItem]) {
            assert_eq!(self.items.len(), expect.len());
            assert!(
                self.items
                    .iter()
                    .zip(expect.iter())
                    .all(|(item, expect)| item.contact_info == expect.contact_info)
            );
            assert!(self.items.iter().is_sorted_by_key(|item| item.last_seen));
        }
    }
}

#[cfg(test)]
mod tests {
    use crate::NODE_ID_BIT_SIZE;

    use super::*;

    #[test]
    fn kbucket_sorted() {
        let item_1 = KBucketItem::new(NodeContactInfo::new_mock(1));
        let item_2 = KBucketItem::new(NodeContactInfo::new_mock(2));
        let item_3 = KBucketItem::new(NodeContactInfo::new_mock(3));
        assert!(item_1.last_seen < item_2.last_seen && item_2.last_seen < item_3.last_seen);

        let mut kbucket = KBucket::new(10);
        assert_eq!(kbucket.insert(item_1.clone()), Ok(()));
        assert_eq!(kbucket.insert(item_2.clone()), Ok(()));
        assert_eq!(kbucket.insert(item_3.clone()), Ok(()));
        kbucket.assert_items(&[&item_1, &item_2, &item_3]);

        let mut kbucket = KBucket::new(10);
        assert_eq!(kbucket.insert(item_3.clone()), Ok(()));
        assert_eq!(kbucket.insert(item_2.clone()), Ok(()));
        assert_eq!(kbucket.insert(item_1.clone()), Ok(()));
        kbucket.assert_items(&[&item_1, &item_2, &item_3]);

        let mut kbucket = KBucket::new(10);
        assert_eq!(kbucket.insert(item_1.clone()), Ok(()));
        assert_eq!(kbucket.insert(item_3.clone()), Ok(()));
        assert_eq!(kbucket.insert(item_2.clone()), Ok(()));
        kbucket.assert_items(&[&item_1, &item_2, &item_3]);
    }

    #[test]
    fn split() {
        let mut kbucket = KBucket::new_mock(
            10,
            [
                0b0000_0000_0000_0010,
                0b0000_0000_0000_0011,
                0b0000_0000_0000_0100,
                0b0000_0000_0000_0111,
                //                ^ bit 13
            ]
            .into_iter()
            .map(|port| KBucketItem::new(NodeContactInfo::new_mock(port))),
        );
        let (left, right) = kbucket.split(13);
        kbucket.assert_items(&[]);
        left.assert_items(&[
            &KBucketItem::new(NodeContactInfo::new_mock(0b0000_0000_0000_0100)),
            &KBucketItem::new(NodeContactInfo::new_mock(0b0000_0000_0000_0111)),
        ]);
        right.assert_items(&[
            &KBucketItem::new(NodeContactInfo::new_mock(0b0000_0000_0000_0010)),
            &KBucketItem::new(NodeContactInfo::new_mock(0b0000_0000_0000_0011)),
        ]);
        assert_eq!(kbucket.max_bucket_size, 10);
        assert_eq!(left.max_bucket_size, 10);
        assert_eq!(right.max_bucket_size, 10);
    }

    #[test]
    fn split_deepest() {
        let zero = KBucketItem::new(NodeContactInfo::new_mock(0));
        for bit_index in 0..NODE_ID_BIT_SIZE {
            let mut kbucket = KBucket::new_mock(1, [zero.clone()].into_iter());
            let (left, right) = kbucket.split(bit_index);
            kbucket.assert_items(&[]);
            left.assert_items(&[]);
            right.assert_items(&[&zero]);
        }
    }

    #[test]
    fn insert() {
        let mut kbucket = KBucket::new(10);
        kbucket.assert_items(&[]);

        let item_1 = KBucketItem::new(NodeContactInfo::new_mock(1));
        assert_eq!(kbucket.insert(item_1.clone()), Ok(()));
        kbucket.assert_items(&[&item_1]);

        let item_2 = KBucketItem::new(NodeContactInfo::new_mock(2));
        assert_eq!(kbucket.insert(item_2.clone()), Ok(()));
        kbucket.assert_items(&[&item_1, &item_2]);

        let item_3 = KBucketItem::new(NodeContactInfo::new_mock(3));
        assert_eq!(kbucket.insert(item_3.clone()), Ok(()));
        kbucket.assert_items(&[&item_1, &item_2, &item_3]);

        let new_item = KBucketItem::new(NodeContactInfo::new_mock(1));
        assert_eq!(kbucket.insert(new_item.clone()), Ok(()));
        kbucket.assert_items(&[&item_2, &item_3, &item_1]);
        assert_eq!(kbucket.items[2].last_seen, new_item.last_seen);

        for _ in 0..3 {
            let new_item = KBucketItem::new(NodeContactInfo::new_mock(3));
            assert_eq!(kbucket.insert(new_item.clone()), Ok(()));
            kbucket.assert_items(&[&item_2, &item_1, &item_3]);
            assert_eq!(kbucket.items[2].last_seen, new_item.last_seen);
        }
    }

    #[test]
    fn insert_address_change() {
        let mut kbucket = KBucket::new(10);
        kbucket.assert_items(&[]);

        let item_1 = KBucketItem::new(NodeContactInfo::new_mock(1));
        for _ in 0..3 {
            assert_eq!(kbucket.insert(item_1.clone()), Ok(()));
            kbucket.assert_items(&[&item_1]);
        }

        let mut item_2 = item_1.clone();
        item_2.contact_info.endpoint.set_port(2);
        assert_ne!(item_1, item_2);
        assert_eq!(kbucket.insert(item_2.clone()), Ok(()));
        kbucket.assert_items(&[&item_2]);
    }

    #[test]
    fn insert_full() {
        let mut kbucket = KBucket::new(10);
        kbucket.assert_items(&[]);

        let items: Vec<_> = (0u16..10)
            .map(|i| KBucketItem::new(NodeContactInfo::new_mock(i)))
            .collect();
        let expect = items.iter().collect::<Vec<_>>();

        for item in &items {
            assert_eq!(kbucket.insert(item.clone()), Ok(()));
        }
        kbucket.assert_items(&expect);

        let item = KBucketItem::new(NodeContactInfo::new_mock(10));
        assert_eq!(kbucket.insert(item.clone()), Err(item.clone()));
        kbucket.assert_items(&expect);
    }

    #[test]
    fn remove() {
        let x = NodeContactInfo::new_mock(1);
        let y = NodeContactInfo::new_mock(2);
        let mut item = KBucketItem::new(x.clone());
        item.contact_info.endpoint.set_port(3);
        assert_ne!(item.contact_info, x);

        let mut kbucket = KBucket::new(10);
        kbucket.assert_items(&[]);

        assert_eq!(kbucket.remove(&x), None);

        assert_eq!(kbucket.insert(item.clone()), Ok(()));
        kbucket.assert_items(&[&item]);

        assert_eq!(kbucket.remove(&y), None);
        kbucket.assert_items(&[&item]);

        assert_eq!(kbucket.remove(&x), Some(item.clone()));
        kbucket.assert_items(&[]);
    }
}
