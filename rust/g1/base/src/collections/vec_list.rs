//! Linked list implemented by `Vec`.
//!
//! Compared to `Vec`, `VecList` has the advantage that insertion and removal of nodes are `O(1)`,
//! and node positions are stable -- they do not shift after insertions or removals.
//!
//! Compared to stdlib's `LinkedList`, `VecList` has the advantage that its cursor does not borrow
//! from the list and can, therefore, be shared more freely.  However, it is your responsibility to
//! stop using a cursor after its node is removed; otherwise, the cursor will point to a free node
//! or a reused node.

use std::fmt::{self, Debug};
use std::iter;
use std::ops::{Index, IndexMut};

#[derive(Clone)]
pub struct VecList<T> {
    nodes: Vec<Node<T>>,
    len: usize,
    // While `VecList` is not circular, `used` and `free` are circular for convenience.
    //
    // TODO: Is it preferable to use `usize::MAX` as the sentinel value instead of `None`?
    used: Option<usize>,
    free: Option<usize>,
}

/// Cursor of `VecList`.
///
/// NOTE: `VecList`'s cursor differs from stdlib `LinkedList`'s cursor in two aspects:
/// * It points to a node, rather than resting between two nodes.
/// * It does not go circles.
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct Cursor(usize);

#[derive(Clone, Debug)]
struct Node<T> {
    value: Option<T>,
    prev: usize,
    next: usize,
}

impl<T> VecList<T> {
    pub fn new() -> Self {
        Self {
            nodes: Vec::new(),
            len: 0,
            used: None,
            free: None,
        }
    }

    pub fn with_capacity(capacity: usize) -> Self {
        Self {
            nodes: Vec::with_capacity(capacity),
            len: 0,
            used: None,
            free: None,
        }
    }
}

impl<T> Default for VecList<T> {
    fn default() -> Self {
        Self::new()
    }
}

impl<T> Extend<T> for VecList<T> {
    fn extend<I>(&mut self, iter: I)
    where
        I: IntoIterator<Item = T>,
    {
        for value in iter {
            self.push_back(value);
        }
    }
}

impl<T, const N: usize> From<[T; N]> for VecList<T> {
    fn from(arr: [T; N]) -> Self {
        let mut list = Self::with_capacity(N);
        list.extend(arr);
        list
    }
}

impl<T> FromIterator<T> for VecList<T> {
    fn from_iter<I>(iter: I) -> Self
    where
        I: IntoIterator<Item = T>,
    {
        let mut list = Self::new();
        list.extend(iter);
        list
    }
}

impl<T> Debug for VecList<T>
where
    T: Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_list().entries(self.iter()).finish()
    }
}

impl<T> PartialEq for VecList<T>
where
    T: PartialEq,
{
    fn eq(&self, other: &Self) -> bool {
        self.len() == other.len() && self.iter().eq(other.iter())
    }
}

impl<T> Eq for VecList<T> where T: Eq {}

impl<T> VecList<T> {
    pub fn capacity(&self) -> usize {
        self.nodes.capacity()
    }

    pub fn is_empty(&self) -> bool {
        self.len == 0
    }

    pub fn len(&self) -> usize {
        self.len
    }

    pub fn iter(&self) -> impl Iterator<Item = &T> {
        let mut cursor = self.cursor_front();
        iter::from_fn(move || {
            let this = cursor?;
            cursor = self.next(this);
            Some(self.get_impl(this))
        })
    }

    // TODO: Implement an `iter_mut` that satisfies the borrow checker.

    pub fn cursor_front(&self) -> Option<Cursor> {
        Some(Cursor(self.used?))
    }

    pub fn cursor_back(&self) -> Option<Cursor> {
        Some(Cursor(self.nodes[self.used?].prev))
    }

    pub fn front(&self) -> Option<&T> {
        self.cursor_front().map(|p| self.get_impl(p))
    }

    pub fn front_mut(&mut self) -> Option<&mut T> {
        self.cursor_front().map(|p| self.get_mut_impl(p))
    }

    pub fn back(&self) -> Option<&T> {
        self.cursor_back().map(|p| self.get_impl(p))
    }

    pub fn back_mut(&mut self) -> Option<&mut T> {
        self.cursor_back().map(|p| self.get_mut_impl(p))
    }

    pub fn get(&self, cursor: Cursor) -> Option<&T> {
        if self.is_null(cursor) {
            None
        } else {
            Some(self.get_impl(cursor))
        }
    }

    pub fn get_mut(&mut self, cursor: Cursor) -> Option<&mut T> {
        if self.is_null(cursor) {
            None
        } else {
            Some(self.get_mut_impl(cursor))
        }
    }

    fn get_impl(&self, cursor: Cursor) -> &T {
        self.nodes[cursor.0].value.as_ref().unwrap()
    }

    fn get_mut_impl(&mut self, cursor: Cursor) -> &mut T {
        self.nodes[cursor.0].value.as_mut().unwrap()
    }

    pub fn push_front(&mut self, value: T) -> Cursor {
        let new = self.new_node(value);
        match self.used {
            Some(used) => list_insert_prev(&mut self.nodes, used, new),
            None => list_link(&mut self.nodes, new, new),
        }
        self.used = Some(new);
        self.len += 1;
        Cursor(new)
    }

    pub fn push_back(&mut self, value: T) -> Cursor {
        let new = self.new_node(value);
        match self.used {
            Some(used) => list_insert_prev(&mut self.nodes, used, new),
            None => {
                list_link(&mut self.nodes, new, new);
                self.used = Some(new);
            }
        }
        self.len += 1;
        Cursor(new)
    }

    pub fn insert_prev(&mut self, cursor: Cursor, value: T) -> Cursor {
        assert!(!self.is_null(cursor));
        let new = self.new_node(value);
        list_insert_prev(&mut self.nodes, cursor.0, new);
        if cursor.0 == self.used.unwrap() {
            self.used = Some(new);
        }
        self.len += 1;
        Cursor(new)
    }

    pub fn insert_next(&mut self, cursor: Cursor, value: T) -> Cursor {
        assert!(!self.is_null(cursor));
        let new = self.new_node(value);
        list_insert_next(&mut self.nodes, cursor.0, new);
        self.len += 1;
        Cursor(new)
    }

    pub fn pop_front(&mut self) -> Option<T> {
        self.cursor_front().map(|p| self.remove(p))
    }

    pub fn pop_back(&mut self) -> Option<T> {
        self.cursor_back().map(|p| self.remove(p))
    }

    pub fn remove(&mut self, cursor: Cursor) -> T {
        assert!(!self.is_null(cursor));
        if list_is_single(&self.nodes, cursor.0) {
            self.used = None;
        } else if cursor.0 == self.used.unwrap() {
            self.used = Some(self.nodes[cursor.0].next)
        }
        list_remove(&mut self.nodes, cursor.0);
        let value = self.nodes[cursor.0].value.take().unwrap();
        self.len -= 1;

        match self.free {
            Some(free) => list_insert_prev(&mut self.nodes, free, cursor.0),
            None => {
                list_link(&mut self.nodes, cursor.0, cursor.0);
                self.free = Some(cursor.0);
            }
        }
        self.cleanup_free_list();

        value
    }

    pub fn move_front(&mut self, cursor: Cursor) {
        assert!(!self.is_null(cursor));
        let used = self.used.unwrap();
        if cursor.0 == used {
            // Nothing to do here.
        } else {
            list_remove(&mut self.nodes, cursor.0);
            list_insert_prev(&mut self.nodes, used, cursor.0);
            self.used = Some(self.nodes[used].prev);
        }
    }

    pub fn move_back(&mut self, cursor: Cursor) {
        assert!(!self.is_null(cursor));
        let used = self.used.unwrap();
        if cursor.0 == used {
            self.used = Some(self.nodes[used].next);
        } else {
            list_remove(&mut self.nodes, cursor.0);
            list_insert_prev(&mut self.nodes, used, cursor.0);
        }
    }

    pub fn clear(&mut self) {
        self.nodes.clear();
        self.len = 0;
        self.used = None;
        self.free = None;
    }

    //
    // Cursor Methods
    //

    pub fn is_null(&self, cursor: Cursor) -> bool {
        self.nodes
            .get(cursor.0)
            .map(|node| node.is_free())
            .unwrap_or(true)
    }

    pub fn prev(&self, cursor: Cursor) -> Option<Cursor> {
        if cursor.0 == self.used? {
            None
        } else {
            let node = self.nodes.get(cursor.0)?;
            (!node.is_free()).then_some(Cursor(node.prev))
        }
    }

    pub fn next(&self, cursor: Cursor) -> Option<Cursor> {
        if cursor.0 == self.nodes[self.used?].prev {
            None
        } else {
            let node = self.nodes.get(cursor.0)?;
            (!node.is_free()).then_some(Cursor(node.next))
        }
    }

    //
    // Helpers
    //

    /// Reuses a free node when available, or allocates a new one.
    ///
    /// NOTE: The `prev` and `next` of the returned node are not initialized.
    fn new_node(&mut self, value: T) -> usize {
        match self.free {
            Some(free) => {
                if list_is_single(&self.nodes, free) {
                    self.free = None;
                } else {
                    self.free = Some(self.nodes[free].next);
                    list_remove(&mut self.nodes, free);
                }
                self.nodes[free].assign(value);
                free
            }
            None => {
                self.nodes.push(Node::new(value));
                self.nodes.len() - 1
            }
        }
    }

    /// Cleans up free nodes at the end of `nodes`.
    fn cleanup_free_list(&mut self) {
        while self
            .nodes
            .last()
            .map(|node| node.is_free())
            .unwrap_or(false)
        {
            let i = self.nodes.len() - 1;
            if list_is_single(&self.nodes, i) {
                self.free = None;
            } else {
                if i == self.free.unwrap() {
                    self.free = Some(self.nodes[i].next);
                }
                list_remove(&mut self.nodes, i);
            }
            self.nodes.pop();
        }
    }
}

impl<T> Index<Cursor> for VecList<T> {
    type Output = T;

    fn index(&self, cursor: Cursor) -> &Self::Output {
        self.get_impl(cursor)
    }
}

impl<T> IndexMut<Cursor> for VecList<T> {
    fn index_mut(&mut self, cursor: Cursor) -> &mut Self::Output {
        self.get_mut_impl(cursor)
    }
}

impl<T> Node<T> {
    fn new(value: T) -> Self {
        Self {
            value: Some(value),
            prev: usize::MAX,
            next: usize::MAX,
        }
    }

    fn is_free(&self) -> bool {
        self.value.is_none()
    }

    fn assign(&mut self, value: T) {
        assert!(self.is_free());
        self.value = Some(value);
    }
}

//
// Low-level methods for circular doubly linked lists.
//

fn list_is_single<T>(nodes: &[Node<T>], i: usize) -> bool {
    nodes[i].prev == i && nodes[i].next == i
}

fn list_insert_prev<T>(nodes: &mut [Node<T>], target: usize, source: usize) {
    list_link(nodes, nodes[target].prev, source);
    list_link(nodes, source, target);
}

fn list_insert_next<T>(nodes: &mut [Node<T>], target: usize, source: usize) {
    list_link(nodes, source, nodes[target].next);
    list_link(nodes, target, source);
}

fn list_remove<T>(nodes: &mut [Node<T>], target: usize) {
    list_link(nodes, nodes[target].prev, nodes[target].next);
}

fn list_link<T>(nodes: &mut [Node<T>], i: usize, j: usize) {
    nodes[i].next = j;
    nodes[j].prev = i;
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl<T> VecList<T>
    where
        T: Debug + PartialEq,
    {
        pub fn assert_list(&self, expect: &[T], num_frees: usize) {
            assert_eq!(self.is_empty(), expect.is_empty());
            assert_eq!(self.len(), expect.len());
            assert!(self.iter().eq(expect.iter()));

            assert_eq!(self.front(), expect.first());
            assert_eq!(self.back(), expect.last());

            assert_eq!(self.nodes.len(), expect.len() + num_frees);
            assert_eq!(self.len, expect.len());
            assert_eq!(self.used.is_none(), expect.is_empty());
            assert_eq!(self.free.is_none(), num_frees == 0);

            if !expect.is_empty() {
                let mut i = self.used.unwrap();
                for value in expect {
                    assert_eq!(self.nodes[i].value.as_ref(), Some(value));
                    i = self.nodes[i].next;
                }
                assert_eq!(i, self.used.unwrap());

                i = self.nodes[i].prev;
                for value in expect.iter().rev() {
                    assert_eq!(self.nodes[i].value.as_ref(), Some(value));
                    i = self.nodes[i].prev;
                }
                assert_eq!(i, self.nodes[self.used.unwrap()].prev);
            }

            if num_frees > 0 {
                let mut i = self.free.unwrap();
                for _ in 0..num_frees {
                    assert_eq!(self.nodes[i].value, None);
                    i = self.nodes[i].next;
                }
                assert_eq!(i, self.free.unwrap());

                i = self.nodes[i].prev;
                for _ in 0..num_frees {
                    assert_eq!(self.nodes[i].value, None);
                    i = self.nodes[i].prev;
                }
                assert_eq!(i, self.nodes[self.free.unwrap()].prev);
            }
        }
    }

    impl Cursor {
        pub fn new(index: usize) -> Self {
            Self(index)
        }
    }

    impl From<Cursor> for usize {
        fn from(cursor: Cursor) -> Self {
            cursor.0
        }
    }

    impl<T> PartialEq for Node<T>
    where
        T: PartialEq,
    {
        fn eq(&self, other: &Self) -> bool {
            self.value == other.value && self.prev == other.prev && self.next == other.next
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn n(value: Option<usize>, prev: usize, next: usize) -> Node<usize> {
        Node { value, prev, next }
    }

    #[test]
    fn new() {
        let list1 = VecList::<usize>::new();
        list1.assert_list(&[], 0);
        assert_eq!(list1.capacity(), 0);

        let list2 = VecList::with_capacity(4);
        list2.assert_list(&[], 0);
        assert_eq!(list2.capacity(), 4);

        assert_eq!(list1, list2);
        assert_ne!(list1.capacity(), list2.capacity());

        VecList::<usize>::default().assert_list(&[], 0);

        VecList::from([100]).assert_list(&[100], 0);
        VecList::from([100, 101]).assert_list(&[100, 101], 0);
        VecList::from([100, 101, 102]).assert_list(&[100, 101, 102], 0);
    }

    #[test]
    fn eq() {
        let list1 = VecList::from([100, 101, 102]);
        let mut list2 = VecList::from([99, 100, 101, 102]);
        list2.remove(list2.cursor_front().unwrap());
        assert_ne!(list1.nodes, list2.nodes);
        assert_eq!(list1, list2);

        assert_ne!(VecList::from([100]), VecList::new());
        assert_ne!(VecList::from([100, 101]), VecList::from([101, 100]));
    }

    #[test]
    fn get() {
        let mut list = VecList::from([100, 101]);
        let p = list.cursor_front().unwrap();
        let q = list.cursor_back().unwrap();

        assert_eq!(list.get(p), Some(&100));
        assert_eq!(list.get(q), Some(&101));
        assert_eq!(list.get(Cursor(2)), None);

        assert_eq!(list.get_mut(p), Some(&mut 100));
        assert_eq!(list.get_mut(q), Some(&mut 101));
        assert_eq!(list.get_mut(Cursor(2)), None);

        assert_eq!(list[p], 100);
        assert_eq!(list[q], 101);
    }

    #[test]
    fn push_front() {
        let mut list = VecList::new();
        list.assert_list(&[], 0);

        assert_eq!(list.push_front(100), Cursor(0));
        let p = list.cursor_front().unwrap();
        let q = list.cursor_back().unwrap();
        list.assert_list(&[100], 0);
        assert_eq!(list[p], 100);
        assert_eq!(list[q], 100);

        assert_eq!(list.push_front(101), Cursor(1));
        list.assert_list(&[101, 100], 0);
        assert_eq!(list[p], 100);
        assert_eq!(list[q], 100);

        assert_eq!(list.push_front(102), Cursor(2));
        list.assert_list(&[102, 101, 100], 0);
        assert_eq!(list[p], 100);
        assert_eq!(list[q], 100);
    }

    #[test]
    fn push_back() {
        let mut list = VecList::new();
        list.assert_list(&[], 0);

        assert_eq!(list.push_back(100), Cursor(0));
        let p = list.cursor_front().unwrap();
        let q = list.cursor_back().unwrap();
        list.assert_list(&[100], 0);
        assert_eq!(list[p], 100);
        assert_eq!(list[q], 100);

        assert_eq!(list.push_back(101), Cursor(1));
        list.assert_list(&[100, 101], 0);
        assert_eq!(list[p], 100);
        assert_eq!(list[q], 100);

        assert_eq!(list.push_back(102), Cursor(2));
        list.assert_list(&[100, 101, 102], 0);
        assert_eq!(list[p], 100);
        assert_eq!(list[q], 100);
    }

    #[test]
    fn insert() {
        let mut list = VecList::from([100]);
        let p = list.cursor_front().unwrap();
        list.assert_list(&[100], 0);
        assert_eq!(list[p], 100);

        assert_eq!(list.insert_prev(p, 99), Cursor(1));
        list.assert_list(&[99, 100], 0);
        assert_eq!(list[p], 100);

        assert_eq!(list.insert_prev(p, 98), Cursor(2));
        list.assert_list(&[99, 98, 100], 0);
        assert_eq!(list[p], 100);

        assert_eq!(list.insert_next(p, 101), Cursor(3));
        list.assert_list(&[99, 98, 100, 101], 0);
        assert_eq!(list[p], 100);

        assert_eq!(list.insert_next(p, 102), Cursor(4));
        list.assert_list(&[99, 98, 100, 102, 101], 0);
        assert_eq!(list[p], 100);
    }

    #[test]
    fn remove() {
        let mut list = VecList::from([100]);
        assert_eq!(list.remove(Cursor(0)), 100);
        list.assert_list(&[], 0);

        let mut list = VecList::from([100, 101, 102]);
        assert_eq!(list.remove(Cursor(1)), 101);
        list.assert_list(&[100, 102], 1);
        assert_eq!(list.remove(Cursor(0)), 100);
        list.assert_list(&[102], 2);
        assert_eq!(list.remove(Cursor(2)), 102);
        list.assert_list(&[], 0);

        let mut list = VecList::from([100, 101, 102, 103]);
        assert_eq!(list.remove(Cursor(2)), 102);
        list.assert_list(&[100, 101, 103], 1);
        assert_eq!(list.remove(Cursor(1)), 101);
        list.assert_list(&[100, 103], 2);
        assert_eq!(list.remove(Cursor(0)), 100);
        list.assert_list(&[103], 3);
        assert_eq!(list.remove(Cursor(3)), 103);
        list.assert_list(&[], 0);
    }

    #[test]
    fn move_front() {
        fn test<const N: usize>(testdata: [usize; N]) {
            for i in 0..N {
                let mut expect = testdata;
                let mut list = VecList::from(testdata);
                let mut p = list.cursor_front().unwrap();
                for _ in 0..i {
                    p = list.next(p).unwrap();
                }

                list.assert_list(&expect, 0);
                assert_eq!(list[p], expect[i]);

                list.move_front(p);
                expect[..=i].rotate_right(1);

                list.assert_list(&expect, 0);
                assert_eq!(list[p], expect[0]);
            }
        }

        test([100]);
        test([100, 101]);
        test([100, 101, 102]);
        test([100, 101, 102, 103]);
    }

    #[test]
    fn move_back() {
        fn test<const N: usize>(testdata: [usize; N]) {
            for i in 0..N {
                let mut expect = testdata;
                let mut list = VecList::from(testdata);
                let mut p = list.cursor_front().unwrap();
                for _ in 0..i {
                    p = list.next(p).unwrap();
                }

                list.assert_list(&expect, 0);
                assert_eq!(list[p], expect[i]);

                list.move_back(p);
                expect[i..].rotate_left(1);

                list.assert_list(&expect, 0);
                assert_eq!(list[p], expect[N - 1]);
            }
        }

        test([100]);
        test([100, 101]);
        test([100, 101, 102]);
        test([100, 101, 102, 103]);
    }

    #[test]
    fn clear() {
        let mut list = VecList::from([100, 101, 102]);
        list.pop_front();
        list.assert_list(&[101, 102], 1);

        list.clear();
        list.assert_list(&[], 0);
    }

    #[test]
    fn is_null() {
        let mut list = VecList::from([100, 101]);

        assert_eq!(list.is_null(Cursor(2)), true);

        let p = list.cursor_front().unwrap();
        assert_eq!(p, Cursor(0));
        assert_eq!(list.is_null(p), false);

        list.pop_front();
        list.assert_list(&[101], 1);
        assert_eq!(list.is_null(p), true);

        // Reuse `list.nodes[0]`.
        list.push_back(102);
        list.assert_list(&[101, 102], 0);
        assert_eq!(list.is_null(p), false);
    }

    #[test]
    fn prev_and_next() {
        let list = VecList::<usize>::new();
        assert_eq!(list.is_null(Cursor(0)), true);
        assert_eq!(list.prev(Cursor(0)), None);
        assert_eq!(list.next(Cursor(0)), None);

        let list = VecList::from([100]);
        assert_eq!(list.is_null(Cursor(0)), false);
        assert_eq!(list.prev(Cursor(0)), None);
        assert_eq!(list.next(Cursor(0)), None);

        let list = VecList::from([100, 101]);
        assert_eq!(list.is_null(Cursor(0)), false);
        assert_eq!(list.prev(Cursor(0)), None);
        assert_eq!(list.next(Cursor(0)), Some(Cursor(1)));
        assert_eq!(list.is_null(Cursor(1)), false);
        assert_eq!(list.prev(Cursor(1)), Some(Cursor(0)));
        assert_eq!(list.next(Cursor(1)), None);

        let mut list = VecList::from([100, 101, 102]);
        assert_eq!(list.prev(Cursor(1)), Some(Cursor(0)));
        assert_eq!(list.next(Cursor(1)), Some(Cursor(2)));
        assert_eq!(list.remove(Cursor(1)), 101);
        assert_eq!(list.prev(Cursor(1)), None);
        assert_eq!(list.next(Cursor(1)), None);
    }

    #[test]
    fn new_node() {
        let mut list = VecList::from([100, 101, 102]);
        assert_eq!(list.free, None);
        list.pop_front();
        assert_eq!(list.free, Some(0));
        list.pop_front();
        assert_eq!(list.free, Some(0));
        assert_eq!(
            list.nodes,
            vec![n(None, 1, 1), n(None, 0, 0), n(Some(102), 2, 2)],
        );

        assert_eq!(list.new_node(200), 0);
        assert_eq!(list.free, Some(1));
        assert_eq!(
            list.nodes,
            vec![n(Some(200), 1, 1), n(None, 1, 1), n(Some(102), 2, 2)],
        );

        assert_eq!(list.new_node(201), 1);
        assert_eq!(list.free, None);
        assert_eq!(
            list.nodes,
            vec![n(Some(200), 1, 1), n(Some(201), 1, 1), n(Some(102), 2, 2)],
        );

        assert_eq!(list.new_node(202), 3);
        assert_eq!(list.free, None);
        assert_eq!(
            list.nodes,
            vec![
                n(Some(200), 1, 1),
                n(Some(201), 1, 1),
                n(Some(102), 2, 2),
                n(Some(202), usize::MAX, usize::MAX),
            ],
        );
    }

    #[test]
    fn cleanup_free_list() {
        let mut list = VecList::from([100, 101, 102]);
        list.remove(Cursor(1));
        assert_eq!(list.free, Some(1));
        assert_eq!(
            list.nodes,
            vec![n(Some(100), 2, 2), n(None, 1, 1), n(Some(102), 0, 0)],
        );

        list.cleanup_free_list();
        assert_eq!(list.free, Some(1));
        assert_eq!(
            list.nodes,
            vec![n(Some(100), 2, 2), n(None, 1, 1), n(Some(102), 0, 0)],
        );

        list.remove(Cursor(2)); // This calls `cleanup_free_list`.
        assert_eq!(list.free, None);
        assert_eq!(list.nodes, vec![n(Some(100), 0, 0)]);

        list.cleanup_free_list();
        assert_eq!(list.free, None);
        assert_eq!(list.nodes, vec![n(Some(100), 0, 0)]);
    }

    #[test]
    fn test_list_insert_prev() {
        let mut nodes = vec![n(Some(100), 0, 0), n(Some(101), 999, 999)];
        list_insert_prev(&mut nodes, 0, 1);
        assert_eq!(nodes, vec![n(Some(100), 1, 1), n(Some(101), 0, 0)]);

        let mut nodes = vec![
            n(Some(100), 1, 1),
            n(Some(101), 0, 0),
            n(Some(102), 999, 999),
        ];
        list_insert_prev(&mut nodes, 0, 2);
        assert_eq!(
            nodes,
            vec![n(Some(100), 2, 1), n(Some(101), 0, 2), n(Some(102), 1, 0)],
        );
    }

    #[test]
    fn test_list_insert_next() {
        let mut nodes = vec![n(Some(100), 0, 0), n(Some(101), 999, 999)];
        list_insert_next(&mut nodes, 0, 1);
        assert_eq!(nodes, vec![n(Some(100), 1, 1), n(Some(101), 0, 0)]);

        let mut nodes = vec![
            n(Some(100), 1, 1),
            n(Some(101), 0, 0),
            n(Some(102), 999, 999),
        ];
        list_insert_next(&mut nodes, 0, 2);
        assert_eq!(
            nodes,
            vec![n(Some(100), 1, 2), n(Some(101), 2, 0), n(Some(102), 0, 1)],
        );
    }

    #[test]
    fn test_list_remove() {
        let mut nodes = vec![n(Some(100), 0, 0)];
        list_remove(&mut nodes, 0);
        assert_eq!(nodes, vec![n(Some(100), 0, 0)]);

        let mut nodes = vec![n(Some(100), 1, 1), n(Some(101), 0, 0)];
        list_remove(&mut nodes, 0);
        assert_eq!(nodes, vec![n(Some(100), 1, 1), n(Some(101), 1, 1)]);

        let mut nodes = vec![n(Some(100), 2, 1), n(Some(101), 0, 2), n(Some(102), 1, 0)];
        list_remove(&mut nodes, 0);
        assert_eq!(
            nodes,
            vec![n(Some(100), 2, 1), n(Some(101), 2, 2), n(Some(102), 1, 1)],
        );
    }

    #[test]
    fn test_list_link() {
        let mut nodes = vec![n(Some(100), 0, 0)];
        list_link(&mut nodes, 0, 0);
        assert_eq!(nodes, vec![n(Some(100), 0, 0)]);

        let mut nodes = vec![n(Some(100), 0, 0), n(Some(101), 1, 1)];
        list_link(&mut nodes, 0, 1);
        assert_eq!(nodes, vec![n(Some(100), 0, 1), n(Some(101), 0, 1)]);
        list_link(&mut nodes, 1, 0);
        assert_eq!(nodes, vec![n(Some(100), 1, 1), n(Some(101), 0, 0)]);
    }
}
