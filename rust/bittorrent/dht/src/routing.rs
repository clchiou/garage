use std::collections::VecDeque;
use std::iter;

use bitvec::prelude::*;

use crate::{
    kbucket::{KBucket, KBucketItem},
    Distance, NodeContactInfo, NodeId, NodeIdBitSlice, NODE_ID_BIT_SIZE,
};

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct RoutingTable {
    root: Tree,
    self_id: NodeId,
}

pub(crate) type KBucketPrefix = BitVec<u8, Msb0>;

pub(crate) type KBucketFull = (Vec<NodeContactInfo>, KBucketItem);

#[derive(Clone, Debug, Eq, PartialEq)]
enum Tree {
    Branch(Branch),
    Leaf(Leaf),
}

// When the bit is true, go to the left branch.
#[derive(Clone, Debug, Eq, PartialEq)]
struct Branch {
    left: Box<Tree>,
    right: Box<Tree>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Leaf {
    kbucket: KBucket,
    may_split: bool, // `may_split` is true if `self_id` belongs to this bucket.
}

impl RoutingTable {
    pub(crate) fn new(self_id: NodeId) -> Self {
        Self::with_max_bucket_size(self_id, *crate::k())
    }

    pub(crate) fn with_max_bucket_size(self_id: NodeId, max_bucket_size: usize) -> Self {
        Self {
            root: Tree::leaf(KBucket::new(max_bucket_size), true),
            self_id,
        }
    }

    /// Iterates through the tree and returns `KBucket` and its prefix.
    pub(crate) fn iter(&self) -> impl Iterator<Item = (&KBucket, KBucketPrefix)> {
        let mut stack = VecDeque::from([(&self.root, KBucketPrefix::new())]);
        iter::from_fn(move || {
            while let Some((tree, prefix)) = stack.pop_back() {
                match tree {
                    Tree::Branch(branch) => {
                        let mut right = prefix.clone();
                        let mut left = prefix;
                        right.push(false);
                        left.push(true);
                        stack.push_back((&branch.right, right));
                        stack.push_back((&branch.left, left));
                    }
                    Tree::Leaf(leaf) => return Some((&leaf.kbucket, prefix)),
                }
            }
            None
        })
    }

    pub(crate) fn get_closest(&self, id: &NodeIdBitSlice) -> Vec<NodeContactInfo> {
        self.get_closest_with_limit(id, *crate::k())
    }

    pub(crate) fn get_closest_with_limit(
        &self,
        id: &NodeIdBitSlice,
        limit: usize,
    ) -> Vec<NodeContactInfo> {
        let mut contact_infos = self.root.collect_closest(id, limit);
        contact_infos.sort_by_key(|contact_info| Distance::measure(id, contact_info.id.bits()));
        contact_infos.truncate(limit);
        contact_infos
    }

    // TODO: It feels odd to return clones of all contact info when the `KBucket` is full and
    // cannot be split.  Could we provide a different return value?
    pub(crate) fn insert(&mut self, mut candidate: KBucketItem) -> Result<(), KBucketFull> {
        let (mut tree, bit_index) = self.root.traverse_mut(candidate.contact_info.id.bits());
        for bit_index in bit_index..=NODE_ID_BIT_SIZE {
            let leaf = tree.as_leaf_mut();
            candidate = match leaf.kbucket.insert(candidate) {
                Ok(()) => return Ok(()),
                Err(candidate) => candidate,
            };
            if !leaf.may_split {
                return Err((leaf.kbucket.iter().cloned().collect(), candidate));
            }
            tree.split(bit_index, self.self_id.bits());
            let branch = tree.as_branch_mut();
            tree = if candidate.contact_info.id.bits()[bit_index] {
                &mut branch.left
            } else {
                &mut branch.right
            };
        }
        std::unreachable!()
    }

    pub(crate) fn must_insert(&mut self, candidate: KBucketItem) {
        let (tree, _) = self.root.traverse_mut(candidate.contact_info.id.bits());
        tree.as_leaf_mut().kbucket.must_insert(candidate);
    }

    pub(crate) fn remove(&mut self, contact_info: &NodeContactInfo) -> Option<KBucketItem> {
        let (tree, _) = self.root.traverse_mut(contact_info.id.bits());
        tree.as_leaf_mut().kbucket.remove(contact_info)
    }
}

// TODO: For now, we are using macros because [mutability polymorphism][#414] is still an open
// issue.
//
// [#414]: https://github.com/rust-lang/rfcs/issues/414
macro_rules! generate_traverse {
    ($v:vis $name:ident, $($ref_mut:tt)+ $(,)?) => {
        $v fn $name($($ref_mut)* self, id: &NodeIdBitSlice) -> ($($ref_mut)* Self, usize) {
            let mut tree = self;
            for (i, bit) in id.iter().enumerate() {
                tree = match tree {
                    Self::Branch(branch) => if *bit {
                        $($ref_mut)* branch.left
                    } else {
                        $($ref_mut)* branch.right
                    },
                    Self::Leaf(_) => return (tree, i),
                };
            }
            std::panic!("tree depth exceeds id length: {:?}", id)
        }
    };
}

impl Tree {
    fn branch(left: Self, right: Self) -> Self {
        Self::Branch(Branch {
            left: Box::new(left),
            right: Box::new(right),
        })
    }

    fn leaf(kbucket: KBucket, may_split: bool) -> Self {
        Self::Leaf(Leaf { kbucket, may_split })
    }

    generate_traverse!(traverse_mut, &mut);

    fn as_branch_mut(&mut self) -> &mut Branch {
        match self {
            Self::Branch(branch) => branch,
            Self::Leaf(_) => std::panic!("expect tree branch: {self:?}"),
        }
    }

    fn as_leaf_mut(&mut self) -> &mut Leaf {
        match self {
            Self::Branch(_) => std::panic!("expect tree leaf: {self:?}"),
            Self::Leaf(leaf) => leaf,
        }
    }

    fn collect_closest(&self, id: &NodeIdBitSlice, limit: usize) -> Vec<NodeContactInfo> {
        let mut contact_infos = Vec::with_capacity(limit);
        let mut stack = vec![self];
        let mut bit_index = 0;
        while let Some(tree) = stack.pop() {
            if contact_infos.len() >= limit {
                break;
            }
            match tree {
                Self::Branch(branch) => {
                    if id[bit_index] {
                        stack.push(&branch.right);
                        stack.push(&branch.left);
                    } else {
                        stack.push(&branch.left);
                        stack.push(&branch.right);
                    }
                    bit_index += 1;
                }
                Self::Leaf(leaf) => {
                    contact_infos.extend(leaf.kbucket.iter().cloned());
                }
            }
        }
        contact_infos
    }

    fn split(&mut self, bit_index: usize, self_id: &NodeIdBitSlice) {
        let leaf = self.as_leaf_mut();
        assert!(leaf.may_split);
        let (left, right) = leaf.kbucket.split(bit_index);
        *self = Self::branch(
            Self::leaf(left, self_id[bit_index]),
            Self::leaf(right, !self_id[bit_index]),
        );
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl RoutingTable {
        pub(crate) fn new_mock(max_bucket_size: usize) -> Self {
            Self::with_max_bucket_size(NodeId::min(), max_bucket_size)
        }
    }

    impl Tree {
        generate_traverse!(pub(crate) traverse, &);

        pub(crate) fn as_branch(&self) -> &Branch {
            match self {
                Self::Branch(branch) => branch,
                Self::Leaf(_) => std::panic!("expect tree branch: {:?}", self),
            }
        }

        pub(crate) fn as_leaf(&self) -> &Leaf {
            match self {
                Self::Branch(_) => std::panic!("expect tree leaf: {:?}", self),
                Self::Leaf(leaf) => leaf,
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::net::IpAddr;

    use bitvec::prelude::*;

    use bittorrent_base::NODE_ID_SIZE;

    use super::*;

    fn new_prefix<const N: usize>(prefix: [bool; N]) -> KBucketPrefix {
        KBucketPrefix::from_iter(prefix.into_iter())
    }

    fn assert_iter<const N: usize>(
        table: &RoutingTable,
        expect_items: [&[KBucketItem]; N],
        expect_prefixes: [KBucketPrefix; N],
    ) {
        for (kbucket, expect_items) in table
            .iter()
            .map(|(kbucket, _)| kbucket)
            .zip(expect_items.into_iter())
        {
            let expect_ref_items: Vec<_> = expect_items.iter().collect();
            kbucket.assert_items(&expect_ref_items);
        }
        let prefixes: Vec<_> = table.iter().map(|(_, prefix)| prefix).collect();
        assert_eq!(prefixes, &expect_prefixes);
    }

    fn assert_nodes<'a>(
        nodes: Vec<NodeContactInfo>,
        expect: impl Iterator<Item = &'a NodeContactInfo>,
    ) {
        assert_eq!(nodes, expect.cloned().collect::<Vec<_>>());
    }

    #[test]
    fn table_get_closest() {
        let expect: Vec<_> = [0x8000, 0x4000, 0x2000, 0x1000]
            .into_iter()
            .map(NodeContactInfo::new_mock)
            .collect();
        let items: Vec<_> = expect.iter().cloned().map(KBucketItem::new).collect();

        let mut table = RoutingTable::new_mock(2);
        assert_iter(&table, [&[]], [new_prefix([])]);
        for item in &items {
            assert_eq!(table.insert(item.clone()), Ok(()));
        }
        assert_iter(
            &table,
            [&items[0..1], &items[1..2], &items[2..4]],
            [
                new_prefix([true]),
                new_prefix([false, true]),
                new_prefix([false, false]),
            ],
        );

        for limit in 0..=expect.len() {
            assert_nodes(
                table.get_closest_with_limit(NodeId::min().bits(), limit),
                expect.iter().rev().take(limit),
            );
            assert_nodes(
                table.get_closest_with_limit(NodeId::max().bits(), limit),
                expect.iter().take(limit),
            );
        }

        let mut id = [0x00u8; NODE_ID_SIZE];
        id[0] = 0x20;
        assert_nodes(
            table.get_closest_with_limit(id.view_bits(), 0),
            expect[2..2].iter(),
        );
        assert_nodes(
            table.get_closest_with_limit(id.view_bits(), 1),
            expect[2..3].iter(),
        );
        assert_nodes(
            table.get_closest_with_limit(id.view_bits(), 2),
            expect[2..4].iter(),
        );
        assert_nodes(
            table.get_closest_with_limit(id.view_bits(), 3),
            [&expect[2], &expect[3], &expect[1]].into_iter(),
        );
        assert_nodes(
            table.get_closest_with_limit(id.view_bits(), 4),
            [&expect[2], &expect[3], &expect[1], &expect[0]].into_iter(),
        );
    }

    #[test]
    fn table_insert() {
        fn b(left: Tree, right: Tree) -> Tree {
            Tree::branch(left, right)
        }

        fn l(items: &[KBucketItem], may_split: bool) -> Tree {
            Tree::leaf(KBucket::new_mock(2, items.iter().cloned()), may_split)
        }

        let items: Vec<_> = [0x8000, 0x4000, 0x2000, 0x1000, 0x0800]
            .into_iter()
            .map(NodeContactInfo::new_mock)
            .map(KBucketItem::new)
            .collect();

        let mut table = RoutingTable::new_mock(2);
        assert_eq!(table.root, l(&[], true));
        assert_iter(&table, [&[]], [new_prefix([])]);

        assert_eq!(table.insert(items[0].clone()), Ok(()));
        assert_eq!(table.root, l(&items[0..1], true));
        assert_iter(&table, [&items[0..1]], [new_prefix([])]);

        assert_eq!(table.insert(items[1].clone()), Ok(()));
        assert_eq!(table.root, l(&items[0..2], true));
        assert_iter(&table, [&items[0..2]], [new_prefix([])]);

        assert_eq!(table.insert(items[2].clone()), Ok(()));
        assert_eq!(table.root, b(l(&items[0..1], false), l(&items[1..3], true)));
        assert_iter(
            &table,
            [&items[0..1], &items[1..3]],
            [new_prefix([true]), new_prefix([false])],
        );

        assert_eq!(table.insert(items[3].clone()), Ok(()));
        assert_eq!(
            table.root,
            b(
                l(&items[0..1], false),
                b(l(&items[1..2], false), l(&items[2..4], true)),
            ),
        );
        assert_iter(
            &table,
            [&items[0..1], &items[1..2], &items[2..4]],
            [
                new_prefix([true]),
                new_prefix([false, true]),
                new_prefix([false, false]),
            ],
        );

        assert_eq!(table.insert(items[4].clone()), Ok(()));
        assert_eq!(
            table.root,
            b(
                l(&items[0..1], false),
                b(
                    l(&items[1..2], false),
                    b(l(&items[2..3], false), l(&items[3..5], true)),
                ),
            ),
        );
        assert_iter(
            &table,
            [&items[0..1], &items[1..2], &items[2..3], &items[3..5]],
            [
                new_prefix([true]),
                new_prefix([false, true]),
                new_prefix([false, false, true]),
                new_prefix([false, false, false]),
            ],
        );

        let item_a = KBucketItem::new(NodeContactInfo::new_mock(0x8001));
        let tree = b(
            l(&[items[0].clone(), item_a.clone()], false),
            b(
                l(&items[1..2], false),
                b(l(&items[2..3], false), l(&items[3..5], true)),
            ),
        );
        assert_eq!(table.insert(item_a.clone()), Ok(()));
        assert_eq!(table.root, tree);

        let item_b = KBucketItem::new(NodeContactInfo::new_mock(0x8002));
        assert_eq!(
            table.insert(item_b.clone()),
            Err((
                vec![items[0].contact_info.clone(), item_a.contact_info.clone()],
                item_b.clone(),
            )),
        );
        assert_eq!(table.root, tree);
    }

    #[test]
    fn table_insert_deepest() {
        let mut items: Vec<_> = (0..NODE_ID_BIT_SIZE)
            .map(|i| {
                let mut id = [0u8; NODE_ID_SIZE];
                id.view_bits_mut::<Msb0>().set(i, true);
                let endpoint = (
                    "127.0.0.1".parse::<IpAddr>().unwrap(),
                    u16::try_from(i + 1).unwrap(),
                );
                KBucketItem::new((NodeId::new(id), endpoint.into()).into())
            })
            .collect();
        items.push(KBucketItem::new(NodeContactInfo::new_mock(0)));

        let mut table = RoutingTable::new_mock(1);
        assert_eq!(table.root, Tree::leaf(KBucket::new(1), true));

        for item in &items {
            assert_eq!(table.insert(item.clone()), Ok(()));
        }

        let mut tree = &table.root;
        for i in 0..NODE_ID_BIT_SIZE {
            let branch = tree.as_branch();
            let leaf = branch.left.as_leaf();
            leaf.kbucket.assert_items(&[&items[i]]);
            assert_eq!(leaf.may_split, false);
            tree = &branch.right;
        }
        let leaf = tree.as_leaf();
        leaf.kbucket.assert_items(&[&items[NODE_ID_BIT_SIZE]]);
        assert_eq!(leaf.may_split, true);
    }

    #[test]
    fn table_remove() {
        fn b(left: Tree, right: Tree) -> Tree {
            Tree::branch(left, right)
        }

        fn l(items: &[KBucketItem], may_split: bool) -> Tree {
            Tree::leaf(KBucket::new_mock(2, items.iter().cloned()), may_split)
        }

        let items: Vec<_> = [0x8000, 0x4000, 0x2000, 0x1000]
            .into_iter()
            .map(NodeContactInfo::new_mock)
            .map(KBucketItem::new)
            .collect();

        let mut table = RoutingTable::new_mock(2);
        for item in &items {
            table.insert(item.clone()).unwrap();
        }
        assert_eq!(
            table.root,
            b(
                l(&items[0..1], false),
                b(l(&items[1..2], false), l(&items[2..4], true)),
            ),
        );

        let mut node = items[0].contact_info.clone();
        node.endpoint.set_port(node.endpoint.port() + 1);
        assert_eq!(table.remove(&node), Some(items[0].clone()));
        for _ in 0..3 {
            assert_eq!(
                table.root,
                b(
                    l(&[], false),
                    b(l(&items[1..2], false), l(&items[2..4], true)),
                ),
            );
            assert_eq!(table.remove(&node), None);
        }

        assert_eq!(table.remove(&items[1].contact_info), Some(items[1].clone()));
        for _ in 0..3 {
            assert_eq!(
                table.root,
                b(l(&[], false), b(l(&[], false), l(&items[2..4], true))),
            );
            assert_eq!(table.remove(&items[1].contact_info), None);
        }

        assert_eq!(table.remove(&items[2].contact_info), Some(items[2].clone()));
        for _ in 0..3 {
            assert_eq!(
                table.root,
                b(l(&[], false), b(l(&[], false), l(&items[3..4], true))),
            );
            assert_eq!(table.remove(&items[2].contact_info), None);
        }

        assert_eq!(table.remove(&items[3].contact_info), Some(items[3].clone()));
        for _ in 0..3 {
            assert_eq!(table.root, b(l(&[], false), b(l(&[], false), l(&[], true))));
            assert_eq!(table.remove(&items[3].contact_info), None);
        }
    }

    #[test]
    fn tree_traverse() {
        let tree = Tree::branch(
            Tree::branch(
                Tree::leaf(KBucket::new(1), true),
                Tree::leaf(KBucket::new(2), true),
            ),
            Tree::branch(
                Tree::leaf(KBucket::new(3), true),
                Tree::leaf(KBucket::new(4), true),
            ),
        );

        let (subtree, bit_index) = tree.traverse(0b0000_0000u8.view_bits());
        assert_matches!(subtree, Tree::Leaf(_));
        assert_eq!(subtree.as_leaf().kbucket.max_bucket_size, 4);
        assert_eq!(bit_index, 2);

        let (subtree, bit_index) = tree.traverse(0b0100_0000u8.view_bits());
        assert_matches!(subtree, Tree::Leaf(_));
        assert_eq!(subtree.as_leaf().kbucket.max_bucket_size, 3);
        assert_eq!(bit_index, 2);

        let (subtree, bit_index) = tree.traverse(0b1000_0000u8.view_bits());
        assert_matches!(subtree, Tree::Leaf(_));
        assert_eq!(subtree.as_leaf().kbucket.max_bucket_size, 2);
        assert_eq!(bit_index, 2);

        let (subtree, bit_index) = tree.traverse(0b1100_0000u8.view_bits());
        assert_matches!(subtree, Tree::Leaf(_));
        assert_eq!(subtree.as_leaf().kbucket.max_bucket_size, 1);
        assert_eq!(bit_index, 2);
    }

    #[test]
    #[should_panic(expected = "tree depth exceeds id length: ")]
    fn tree_traverse_panic() {
        let tree = Tree::branch(
            Tree::leaf(KBucket::new(1), true),
            Tree::leaf(KBucket::new(2), true),
        );
        tree.traverse(&0u8.view_bits()[0..1]);
    }

    #[test]
    fn tree_traverse_mut() {
        let mut tree = Tree::branch(
            Tree::branch(
                Tree::leaf(KBucket::new(1), true),
                Tree::leaf(KBucket::new(2), true),
            ),
            Tree::branch(
                Tree::leaf(KBucket::new(3), true),
                Tree::leaf(KBucket::new(4), true),
            ),
        );

        let (subtree, bit_index) = tree.traverse_mut(0b0000_0000u8.view_bits());
        assert_matches!(subtree, Tree::Leaf(_));
        assert_eq!(subtree.as_leaf().kbucket.max_bucket_size, 4);
        assert_eq!(bit_index, 2);

        let (subtree, bit_index) = tree.traverse_mut(0b0100_0000u8.view_bits());
        assert_matches!(subtree, Tree::Leaf(_));
        assert_eq!(subtree.as_leaf().kbucket.max_bucket_size, 3);
        assert_eq!(bit_index, 2);

        let (subtree, bit_index) = tree.traverse_mut(0b1000_0000u8.view_bits());
        assert_matches!(subtree, Tree::Leaf(_));
        assert_eq!(subtree.as_leaf().kbucket.max_bucket_size, 2);
        assert_eq!(bit_index, 2);

        let (subtree, bit_index) = tree.traverse_mut(0b1100_0000u8.view_bits());
        assert_matches!(subtree, Tree::Leaf(_));
        assert_eq!(subtree.as_leaf().kbucket.max_bucket_size, 1);
        assert_eq!(bit_index, 2);
    }

    #[test]
    #[should_panic(expected = "tree depth exceeds id length: ")]
    fn tree_traverse_mut_panic() {
        let mut tree = Tree::branch(
            Tree::leaf(KBucket::new(1), true),
            Tree::leaf(KBucket::new(2), true),
        );
        tree.traverse_mut(&0u8.view_bits()[0..1]);
    }

    #[test]
    fn tree_collect_closest() {
        let nodes: Vec<_> = [0x8000, 0x4000, 0x2000, 0x1000]
            .into_iter()
            .map(NodeContactInfo::new_mock)
            .collect();
        let items: Vec<_> = nodes.iter().cloned().map(KBucketItem::new).collect();
        let tree = Tree::branch(
            Tree::leaf(KBucket::new_mock(2, items[0..1].iter().cloned()), false),
            Tree::branch(
                Tree::leaf(KBucket::new_mock(2, items[1..2].iter().cloned()), false),
                Tree::leaf(KBucket::new_mock(2, items[2..4].iter().cloned()), true),
            ),
        );

        for limit in 0..3 {
            assert_eq!(
                tree.collect_closest([0xffu8, 0xff].view_bits(), limit),
                &nodes[0..limit],
            );
        }
        assert_nodes(
            tree.collect_closest([0xffu8, 0xff].view_bits(), 3),
            nodes.iter(),
        );

        assert_nodes(
            tree.collect_closest([0x00u8, 0x00].view_bits(), 1),
            nodes[2..4].iter(),
        );
        assert_nodes(
            tree.collect_closest([0x00u8, 0x00].view_bits(), 2),
            nodes[2..4].iter(),
        );
        assert_nodes(
            tree.collect_closest([0x00u8, 0x00].view_bits(), 3),
            [&nodes[2], &nodes[3], &nodes[1]].into_iter(),
        );
        assert_nodes(
            tree.collect_closest([0x00u8, 0x00].view_bits(), 4),
            [&nodes[2], &nodes[3], &nodes[1], &nodes[0]].into_iter(),
        );
    }

    #[test]
    fn tree_split() {
        let items: Vec<_> = [0x1000, 0x2000, 0x4000, 0x8000]
            .into_iter()
            .map(NodeContactInfo::new_mock)
            .map(KBucketItem::new)
            .collect();
        let expect: Vec<_> = items.iter().collect();

        let mut tree = Tree::leaf(KBucket::new(10), true);
        let leaf = tree.as_leaf_mut();
        for item in &items {
            leaf.kbucket.insert(item.clone()).unwrap();
        }
        leaf.kbucket.assert_items(&expect);

        for self_id in [
            &[0x00u8, 0x00],
            &[0x10u8, 0x00],
            &[0x20u8, 0x00],
            &[0x40u8, 0x00],
        ] {
            let self_id = self_id.view_bits();
            let mut tree = tree.clone();
            tree.split(0, self_id);
            let branch = tree.as_branch();

            let left = branch.left.as_leaf();
            left.kbucket.assert_items(&expect[3..4]);
            assert_eq!(left.may_split, false);

            let right = branch.right.as_leaf();
            right.kbucket.assert_items(&expect[0..3]);
            assert_eq!(right.may_split, true);

            let (subtree, bit_index) = tree.traverse(self_id);
            assert_eq!(subtree.as_leaf().may_split, true);
            assert_eq!(bit_index, 1);
        }

        {
            let self_id = [0x80u8, 0x00].view_bits();
            let mut tree = tree.clone();
            tree.split(0, self_id);
            let branch = tree.as_branch();

            let left = branch.left.as_leaf();
            left.kbucket.assert_items(&expect[3..4]);
            assert_eq!(left.may_split, true);

            let right = branch.right.as_leaf();
            right.kbucket.assert_items(&expect[0..3]);
            assert_eq!(right.may_split, false);

            let (subtree, bit_index) = tree.traverse(self_id);
            assert_eq!(subtree.as_leaf().may_split, true);
            assert_eq!(bit_index, 1);
        }
    }
}
