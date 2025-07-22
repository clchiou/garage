#![feature(duration_constructors_lite)]
#![cfg_attr(test, feature(assert_matches))]
#![cfg_attr(test, feature(duration_constants))]

mod bucket;
mod refresh;

use std::vec::IntoIter;

use tokio::time::Instant;

use g1_base::collections::Array;

use bt_base::NodeId;
use bt_base::node_id::NODE_ID_BIT_SIZE;
use bt_dht_proto::NodeInfo;

use crate::bucket::{Bucket, BucketItem};
use crate::refresh::RefreshQueue;

pub const K: usize = 8;

pub type Closest = Array<NodeInfo, K>;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Table {
    self_id: NodeId,
    buckets: Vec<Bucket>,
    // I am not sure if this is a good idea, but we track each bucket's "last changed" timer
    // separately from the bucket itself.
    refresh: RefreshQueue,
}

#[derive(Debug)]
pub struct Full {
    item: BucketItem,
    stale: IntoIter<NodeInfo>,
}

impl Table {
    pub fn new(self_id: NodeId) -> Self {
        Self {
            self_id,
            buckets: vec![Bucket::new()],
            refresh: RefreshQueue::new(),
        }
    }

    fn position(&self, id: &NodeId) -> usize {
        self.self_id
            .distance(id)
            .leading_zeros()
            .min(self.buckets.len() - 1)
    }

    // BEP 5 does not specify what the routing table should return when a bucket contains fewer
    // than `K` items.  For now, we iteratively collect items from buckets progressively closer to
    // `self_id` until we have `K` items.
    pub fn get_closest(&self, id: NodeId) -> Closest {
        let mut infos = Array::new();
        for i in self.position(&id)..self.buckets.len() {
            infos.extend(self.buckets[i].iter());
            if infos.is_full() {
                break;
            }
        }
        infos.sort_by_key(|info| info.id.distance(&id));
        infos
    }

    pub fn insert(&mut self, info: NodeInfo, last_ok: Option<Instant>) -> Result<(), Full> {
        // We assume the caller calls `insert` immediately after successfully querying the node.
        let now = last_ok.unwrap_or_else(Instant::now);
        let mut item = BucketItem::new(info, last_ok);
        while self.buckets.len() <= NODE_ID_BIT_SIZE {
            let i = self.position(item.id());

            item = match self.buckets[i].insert(item) {
                Ok(()) => {
                    self.refresh.insert(i, now);
                    return Ok(());
                }
                Err(item) => item,
            };

            if i + 1 < self.buckets.len() {
                return Err(Full {
                    item,
                    stale: self.buckets[i].stale(now).collect::<Vec<_>>().into_iter(),
                });
            }

            let bucket = self.buckets[i].split_off(i, self.self_id.bits()[i]);
            self.buckets.push(bucket);
        }
        unreachable!()
    }

    pub fn update_ok(&mut self, info: NodeInfo) {
        // We assume the caller calls `update_ok` immediately after successfully querying the node.
        let when = Instant::now();
        let i = self.position(&info.id);
        if self.buckets[i].update_ok(info, when) {
            self.refresh.insert(i, when);
        }
    }

    pub fn update_err(&mut self, id: NodeId) {
        let i = self.position(&id);
        self.buckets[i].update_err(id);
    }

    pub fn peek_refresh_deadline(&self) -> Option<Instant> {
        self.refresh.peek().map(|(deadline, _)| *deadline)
    }

    /// Returns the `self_id` prefix length of the bucket to be refreshed.
    pub fn next_refresh(&mut self) -> Option<usize> {
        self.refresh.next().map(|(_, i)| i)
    }
}

impl Iterator for Full {
    type Item = NodeInfo;

    fn next(&mut self) -> Option<Self::Item> {
        self.stale.next()
    }
}

impl Full {
    pub fn ok(&self, table: &mut Table, info: NodeInfo) {
        // We assume the caller calls `ok` immediately after successfully querying the node.
        let when = Instant::now();
        let i = table.position(self.item.id());
        if table.buckets[i].update_ok(info, when) {
            table.refresh.insert(i, when);
        }
    }

    pub fn err(self, table: &mut Table, id: NodeId) -> Option<Self> {
        let Self { item, stale } = self;
        let i = table.position(&id);
        table.buckets[i].remove(id);
        match table.buckets[i].insert(item) {
            Err(item) => Some(Self { item, stale }),
            Ok(()) => None,
        }
    }
}

#[cfg(test)]
mod testing {
    use std::net::{Ipv4Addr, SocketAddrV4};

    use bt_dht_proto::NodeInfo;

    use super::Table;

    impl Table {
        pub(crate) fn assert_infos(&self, expect: &[&[&NodeInfo]]) {
            assert_eq!(self.buckets.len(), expect.len());
            for (bucket, expect) in self.buckets.iter().zip(expect) {
                bucket.assert_infos(expect);
            }
        }
    }

    pub(crate) fn ni(id: [u8; 20], port: u16) -> NodeInfo {
        NodeInfo {
            id: id.into(),
            endpoint: SocketAddrV4::new(Ipv4Addr::LOCALHOST, port).into(),
        }
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use crate::bucket::testing::bi;
    use crate::testing::ni;

    use super::*;

    fn msb(msb: u8) -> [u8; 20] {
        let mut bytes = [0u8; 20];
        bytes[0] = msb;
        bytes
    }

    fn lsb(lsb: u8) -> [u8; 20] {
        let mut bytes = [0u8; 20];
        bytes[bytes.len() - 1] = lsb;
        bytes
    }

    #[test]
    fn position() {
        let msb_80 = NodeId::from(msb(0x80));
        let msb_40 = NodeId::from(msb(0x40));
        let msb_20 = NodeId::from(msb(0x20));
        let msb_00 = NodeId::from(msb(0x00));

        let mut table = Table::new(msb_00.clone());
        table.assert_infos(&[&[]]);
        assert_eq!(table.position(&msb_80), 0);
        assert_eq!(table.position(&msb_40), 0);
        assert_eq!(table.position(&msb_20), 0);
        assert_eq!(table.position(&msb_00), table.buckets.len() - 1);

        table.buckets.push(Bucket::new());
        table.assert_infos(&[&[], &[]]);
        assert_eq!(table.position(&msb_80), 0);
        assert_eq!(table.position(&msb_40), 1);
        assert_eq!(table.position(&msb_20), 1);
        assert_eq!(table.position(&msb_00), table.buckets.len() - 1);

        while table.buckets.len() <= NODE_ID_BIT_SIZE {
            table.buckets.push(Bucket::new());
            assert_eq!(table.position(&msb_80), 0);
            assert_eq!(table.position(&msb_40), 1);
            assert_eq!(table.position(&msb_20), 2);
            assert_eq!(table.position(&msb_00), table.buckets.len() - 1);
        }

        for _ in 0..3 {
            table.buckets.push(Bucket::new());
            assert_eq!(table.position(&msb_80), 0);
            assert_eq!(table.position(&msb_40), 1);
            assert_eq!(table.position(&msb_20), 2);
            assert_eq!(table.position(&msb_00), NODE_ID_BIT_SIZE);
        }
    }

    #[test]
    fn get_closest() {
        let msb_80 = ni(msb(0x80), 8000);
        let msb_40 = ni(msb(0x40), 8000);
        let msb_20 = ni(msb(0x20), 8000);
        let msb_00 = ni(msb(0x00), 8000);

        {
            let mut table = Table::new(msb_00.id.clone());
            for _ in 0..3 {
                table.buckets.push(Bucket::new());
            }
            table.assert_infos(&[&[], &[], &[], &[]]);

            for info in [&msb_80, &msb_40, &msb_20, &msb_00] {
                assert_eq!(&*table.get_closest(info.id.clone()), &[]);
            }
        }

        {
            let mut table = Table::new(msb_00.id.clone());
            for _ in 0..3 {
                table.buckets.push(Bucket::new());
            }
            for info in [&msb_80, &msb_40, &msb_00] {
                let i = table.position(&info.id);
                assert_eq!(table.buckets[i].insert(bi(info, None)), Ok(()));
            }
            table.assert_infos(&[&[&msb_80], &[&msb_40], &[], &[&msb_00]]);

            assert_eq!(
                &*table.get_closest(msb_80.id.clone()),
                // d(msb_00, msb_80) < d(msb_40, msb_80)
                &[msb_80.clone(), msb_00.clone(), msb_40.clone()],
            );
            assert_eq!(
                &*table.get_closest(msb_40.id.clone()),
                &[msb_40.clone(), msb_00.clone()],
            );
            assert_eq!(&*table.get_closest(msb_20.id.clone()), &[msb_00.clone()]);
            assert_eq!(&*table.get_closest(msb_00.id.clone()), &[msb_00.clone()]);
        }

        {
            let mut table = Table::new(msb_00.id.clone());
            table.buckets.push(Bucket::new());
            for b in 0x01..=0x05 {
                let info = ni(msb(0x80 | b), 8000);
                assert_eq!(table.position(&info.id), 0);
                assert_eq!(table.buckets[0].insert(bi(&info, None)), Ok(()));

                let info = ni(msb(0x40 | b), 8000);
                assert_eq!(table.position(&info.id), 1);
                assert_eq!(table.buckets[1].insert(bi(&info, None)), Ok(()));
            }
            assert_eq!(
                &*table.get_closest(msb(0x80).into()),
                &[
                    ni(msb(0x81), 8000),
                    ni(msb(0x82), 8000),
                    ni(msb(0x83), 8000),
                    ni(msb(0x84), 8000),
                    ni(msb(0x85), 8000),
                    // `Bucket::iter` returns items in reverse order.
                    ni(msb(0x43), 8000),
                    ni(msb(0x44), 8000),
                    ni(msb(0x45), 8000),
                ],
            );
        }
    }

    #[tokio::test(start_paused = true)]
    async fn insert() {
        let msb_80 = ni(msb(0x80), 8000);
        let msb_40 = ni(msb(0x40), 8000);
        let msb_00 = ni(msb(0x00), 8000);

        let t0 = Instant::now();

        let mut table = Table::new(msb_00.id.clone());
        table.assert_infos(&[&[]]);

        for _ in 0..3 {
            assert_matches!(table.insert(msb_80.clone(), None), Ok(()));
            table.assert_infos(&[&[&msb_80]]);
        }

        assert_matches!(table.insert(msb_40.clone(), None), Ok(()));
        table.assert_infos(&[&[&msb_80, &msb_40]]);

        assert_matches!(table.insert(msb_00.clone(), None), Ok(()));
        table.assert_infos(&[&[&msb_80, &msb_40, &msb_00]]);

        for _ in 0..3 {
            assert_matches!(table.insert(msb_80.clone(), Some(t0)), Ok(()));
            table.assert_infos(&[&[&msb_40, &msb_00, &msb_80]]);
        }

        assert_matches!(table.insert(msb_80.clone(), None), Ok(()));
        table.assert_infos(&[&[&msb_40, &msb_00, &msb_80]]);
    }

    #[tokio::test(start_paused = true)]
    async fn insert_split() {
        let msb_00 = ni(msb(0x00), 8000);
        let msb_40 = ni(msb(0x40), 8000);
        let msb_80 = ni(msb(0x80), 8000);

        let mut table = Table::new(msb_00.id.clone());
        let mut msb_8x = Vec::new();
        for b in 0x01..=0x08 {
            let info = ni(msb(0x80 | b), 8000);
            assert_matches!(table.insert(info.clone(), None), Ok(()));
            msb_8x.push(info);
        }
        let msb_8x = msb_8x.iter().collect::<Vec<_>>(); // [NodeInfo] -> [&NodeInfo]
        table.assert_infos(&[&*msb_8x]);

        assert_matches!(table.insert(msb_40.clone(), None), Ok(()));
        table.assert_infos(&[&*msb_8x, &[&msb_40]]);

        assert_matches!(table.insert(msb_80.clone(), None), Err(Full { .. }));
        table.assert_infos(&[&*msb_8x, &[&msb_40]]);

        let full = table.insert(msb_80.clone(), None).unwrap_err();
        assert_matches!(full.err(&mut table, msb_8x[3].id.clone()), None);
        table.assert_infos(&[
            &[
                msb_8x[0], msb_8x[1], msb_8x[2], msb_8x[4], msb_8x[5], msb_8x[6], msb_8x[7],
                &msb_80,
            ],
            &[&msb_40],
        ]);
    }

    #[tokio::test(start_paused = true)]
    async fn insert_split_full() {
        let msb_00 = ni(msb(0x00), 8000);
        let msb_80 = ni(msb(0x80), 8000);

        let mut table = Table::new(msb_00.id.clone());
        let mut msb_8x = Vec::new();
        for b in 0x01..=0x08 {
            let info = ni(msb(0x80 | b), 8000);
            assert_matches!(table.insert(info.clone(), None), Ok(()));
            msb_8x.push(info);
        }
        let msb_8x = msb_8x.iter().collect::<Vec<_>>(); // [NodeInfo] -> [&NodeInfo]
        table.assert_infos(&[&*msb_8x]);

        assert_matches!(table.insert(msb_80.clone(), None), Err(Full { .. }));
        table.assert_infos(&[&*msb_8x, &[]]);

        let full = table.insert(msb_80.clone(), None).unwrap_err();
        assert_matches!(full.err(&mut table, msb_8x[0].id.clone()), None);
        table.assert_infos(&[
            &[
                msb_8x[1], msb_8x[2], msb_8x[3], msb_8x[4], msb_8x[5], msb_8x[6], msb_8x[7],
                &msb_80,
            ],
            &[],
        ]);
    }

    #[tokio::test(start_paused = true)]
    async fn insert_split_deep() {
        let lsb_00 = ni(lsb(0x00), 8000);

        let mut table = Table::new(lsb_00.id.clone());
        let mut lsb_0x = Vec::new();
        for b in 0x01..=0x08 {
            let info = ni(lsb(b), 8000);
            assert_matches!(table.insert(info.clone(), None), Ok(()));
            lsb_0x.push(info);
        }
        let lsb_0x = lsb_0x.iter().collect::<Vec<_>>(); // [NodeInfo] -> [&NodeInfo]
        table.assert_infos(&[&*lsb_0x]);

        assert_matches!(table.insert(lsb_00.clone(), None), Ok(()));
        assert_eq!(table.buckets.len(), 152 + 4 + 2);
        for i in 0..152 + 4 {
            table.buckets[i].assert_infos(&[]);
        }
        table.buckets[152 + 4].assert_infos(&[lsb_0x[7]]);
        table.buckets[152 + 4 + 1].assert_infos(&[
            lsb_0x[0], lsb_0x[1], lsb_0x[2], lsb_0x[3], lsb_0x[4], lsb_0x[5], lsb_0x[6], &lsb_00,
        ]);
    }
}
