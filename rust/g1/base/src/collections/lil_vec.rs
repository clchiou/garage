use std::borrow::{Borrow, BorrowMut};
use std::cmp::Ordering;
use std::fmt;
use std::hash::{Hash, Hasher};
use std::iter::FusedIterator;
use std::ops::{Deref, DerefMut, Index, IndexMut};
use std::slice::SliceIndex;
use std::vec;

use super::array::{self, Array};

#[derive(Clone)]
pub enum LilVec<T, const N: usize> {
    Array(Array<T, N>),
    Vec(Vec<T>),
}

macro_rules! dispatch {
    ($self:ident, $this:ident => $expr:expr $(,)?) => {
        match $self {
            Self::Array($this) => $expr,
            Self::Vec($this) => $expr,
        }
    };
}

impl<T, const N: usize> LilVec<T, N> {
    pub fn as_slice(&self) -> &[T] {
        dispatch!(self, this => this.as_slice())
    }

    pub fn as_mut_slice(&mut self) -> &mut [T] {
        dispatch!(self, this => this.as_mut_slice())
    }

    pub fn as_ptr(&self) -> *const T {
        dispatch!(self, this => this.as_ptr())
    }

    pub fn as_mut_ptr(&mut self) -> *mut T {
        dispatch!(self, this => this.as_mut_ptr())
    }

    pub fn capacity(&self) -> usize {
        match self {
            Self::Array(_) => N,
            Self::Vec(vec) => vec.capacity(),
        }
    }

    pub fn reserve(&mut self, additional: usize) {
        match self {
            Self::Array(array) => {
                let n = array.len() + additional;
                if n > N {
                    let mut vec = Vec::with_capacity(n);
                    array.append_to_vec(&mut vec);
                    *self = Self::Vec(vec);
                }
            }
            Self::Vec(vec) => vec.reserve(additional),
        }
    }
}

//
// Construct.
//

impl<T, const N: usize> Default for LilVec<T, N> {
    fn default() -> Self {
        Self::new()
    }
}

impl<T, const N: usize> From<Array<T, N>> for LilVec<T, N> {
    fn from(array: Array<T, N>) -> Self {
        Self::Array(array)
    }
}

impl<T, const N: usize> From<[T; N]> for LilVec<T, N> {
    fn from(array: [T; N]) -> Self {
        Self::Array(array.into())
    }
}

impl<T, const N: usize> From<Vec<T>> for LilVec<T, N> {
    fn from(vec: Vec<T>) -> Self {
        Self::Vec(vec)
    }
}

impl<T, const N: usize> FromIterator<T> for LilVec<T, N> {
    fn from_iter<I>(iter: I) -> Self
    where
        I: IntoIterator<Item = T>,
    {
        let mut this = Self::new();
        this.extend(iter);
        this
    }
}

impl<T, const N: usize> LilVec<T, N> {
    pub fn new() -> Self {
        Self::Array(Array::new())
    }

    pub fn with_capacity(capacity: usize) -> Self {
        if capacity <= N {
            Self::Array(Array::new())
        } else {
            Self::Vec(Vec::with_capacity(capacity))
        }
    }
}

//
// Convert.
//

impl<T, const N: usize> From<LilVec<T, N>> for Vec<T> {
    fn from(other: LilVec<T, N>) -> Self {
        match other {
            LilVec::Array(array) => array.into(),
            LilVec::Vec(vec) => vec,
        }
    }
}

impl<T, const N: usize> LilVec<T, N> {
    pub fn realloc<const M: usize>(self) -> LilVec<T, M> {
        match self {
            Self::Array(array) => array
                .realloc()
                .map_or_else(|array| LilVec::Vec(array.into()), LilVec::Array),
            Self::Vec(vec) => LilVec::Vec(vec),
        }
    }
}

//
// Move.
//

impl<'a, T, const N: usize> From<&'a mut LilVec<T, N>> for Vec<T> {
    fn from(other: &'a mut LilVec<T, N>) -> Self {
        let mut this = Self::with_capacity(other.len());
        other.append_to_vec(&mut this);
        this
    }
}

impl<T, const N: usize> LilVec<T, N> {
    pub fn append<const M: usize>(&mut self, other: &mut LilVec<T, M>) {
        self.reserve(other.len());
        match (self, other) {
            (Self::Array(this), LilVec::Array(that)) => this.append(that),
            (Self::Array(this), LilVec::Vec(that)) => this.append_vec(that),
            (Self::Vec(this), LilVec::Array(that)) => that.append_to_vec(this),
            (Self::Vec(this), LilVec::Vec(that)) => this.append(that),
        }
    }

    pub fn append_vec(&mut self, other: &mut Vec<T>) {
        self.reserve(other.len());
        match self {
            Self::Array(array) => array.append_vec(other),
            Self::Vec(vec) => vec.append(other),
        }
    }

    pub fn append_to_vec(&mut self, other: &mut Vec<T>) {
        match self {
            Self::Array(array) => array.append_to_vec(other),
            Self::Vec(vec) => other.append(vec),
        }
    }
}

//
// Iterate.
//

#[derive(Debug)]
pub enum IntoIter<T, const N: usize> {
    Array(array::IntoIter<T, N>),
    Vec(vec::IntoIter<T>),
}

impl<T, const N: usize> IntoIterator for LilVec<T, N> {
    type Item = T;
    type IntoIter = IntoIter<T, N>;

    fn into_iter(self) -> Self::IntoIter {
        IntoIter::new(self)
    }
}

impl<T, const N: usize> IntoIter<T, N> {
    fn new(this: LilVec<T, N>) -> Self {
        match this {
            LilVec::Array(array) => Self::Array(array.into_iter()),
            LilVec::Vec(vec) => Self::Vec(vec.into_iter()),
        }
    }
}

impl<T, const N: usize> Iterator for IntoIter<T, N> {
    type Item = T;

    fn next(&mut self) -> Option<Self::Item> {
        dispatch!(self, this => this.next())
    }

    fn size_hint(&self) -> (usize, Option<usize>) {
        dispatch!(self, this => this.size_hint())
    }

    fn count(self) -> usize {
        dispatch!(self, this => this.count())
    }

    fn nth(&mut self, n: usize) -> Option<Self::Item> {
        dispatch!(self, this => this.nth(n))
    }

    fn last(self) -> Option<Self::Item> {
        dispatch!(self, this => this.last())
    }
}

impl<T, const N: usize> DoubleEndedIterator for IntoIter<T, N> {
    fn next_back(&mut self) -> Option<Self::Item> {
        dispatch!(self, this => this.next_back())
    }

    fn nth_back(&mut self, n: usize) -> Option<Self::Item> {
        dispatch!(self, this => this.nth_back(n))
    }
}

impl<T, const N: usize> ExactSizeIterator for IntoIter<T, N> {}

impl<T, const N: usize> FusedIterator for IntoIter<T, N> {}

//
// Read.
//

impl<T, const N: usize> fmt::Debug for LilVec<T, N>
where
    T: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> Result<(), fmt::Error> {
        fmt::Debug::fmt(&**self, f)
    }
}

impl<T: Eq, const N: usize> Eq for LilVec<T, N> {}

impl<T, U, const N: usize> PartialEq<LilVec<U, N>> for LilVec<T, N>
where
    T: PartialEq<U>,
{
    fn eq(&self, other: &LilVec<U, N>) -> bool {
        self[..] == other[..]
    }
}

impl<T, const N: usize> Ord for LilVec<T, N>
where
    T: Ord,
{
    fn cmp(&self, other: &Self) -> Ordering {
        Ord::cmp(&**self, &**other)
    }
}

impl<T, const N: usize> PartialOrd for LilVec<T, N>
where
    T: PartialOrd,
{
    fn partial_cmp(&self, other: &LilVec<T, N>) -> Option<Ordering> {
        PartialOrd::partial_cmp(&**self, &**other)
    }
}

impl<T, const N: usize> Hash for LilVec<T, N>
where
    T: Hash,
{
    fn hash<H>(&self, state: &mut H)
    where
        H: Hasher,
    {
        Hash::hash(&**self, state)
    }
}

impl<T, const N: usize> LilVec<T, N> {
    pub fn is_empty(&self) -> bool {
        self.as_slice().is_empty()
    }

    pub fn len(&self) -> usize {
        self.as_slice().len()
    }
}

//
// AsRef/Borrow/Deref.
//

impl<T, const N: usize> Deref for LilVec<T, N> {
    type Target = [T];

    fn deref(&self) -> &Self::Target {
        self.as_slice()
    }
}

impl<T, const N: usize> DerefMut for LilVec<T, N> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        self.as_mut_slice()
    }
}

impl<T, const N: usize> AsRef<[T]> for LilVec<T, N> {
    fn as_ref(&self) -> &[T] {
        self
    }
}

impl<T, const N: usize> AsMut<[T]> for LilVec<T, N> {
    fn as_mut(&mut self) -> &mut [T] {
        self
    }
}

impl<T, const N: usize> Borrow<[T]> for LilVec<T, N> {
    fn borrow(&self) -> &[T] {
        self
    }
}

impl<T, const N: usize> BorrowMut<[T]> for LilVec<T, N> {
    fn borrow_mut(&mut self) -> &mut [T] {
        self
    }
}

//
// Index.
//

impl<T, I, const N: usize> Index<I> for LilVec<T, N>
where
    I: SliceIndex<[T]>,
{
    type Output = I::Output;

    fn index(&self, index: I) -> &Self::Output {
        Index::index(&**self, index)
    }
}

impl<T, I, const N: usize> IndexMut<I> for LilVec<T, N>
where
    I: SliceIndex<[T]>,
{
    fn index_mut(&mut self, index: I) -> &mut Self::Output {
        IndexMut::index_mut(&mut **self, index)
    }
}

//
// Write.
//

impl<T, const N: usize> Extend<T> for LilVec<T, N> {
    fn extend<I>(&mut self, iter: I)
    where
        I: IntoIterator<Item = T>,
    {
        // TODO: Optimize this the way the stdlib does?
        let iter = iter.into_iter();
        // TODO: How should we use the `size_hint` value?
        self.reserve(iter.size_hint().0);
        for value in iter {
            self.push(value);
        }
    }
}

impl<T, const N: usize> LilVec<T, N> {
    pub fn clear(&mut self) {
        dispatch!(self, this => this.clear());
    }

    pub fn insert(&mut self, index: usize, element: T) {
        self.reserve(1);
        dispatch!(self, this => this.insert(index, element))
    }

    pub fn push(&mut self, value: T) {
        self.reserve(1);
        dispatch!(self, this => this.push(value))
    }

    pub fn remove(&mut self, index: usize) -> T {
        dispatch!(self, this => this.remove(index))
    }

    pub fn pop(&mut self) -> Option<T> {
        dispatch!(self, this => this.pop())
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use super::super::array::test_harness::*;
    use super::*;

    impl Alloc {
        fn alloc_lil_vec<const N: usize>(&self, testdata: &[u8]) -> LilVec<Scoped, N> {
            LilVec::from_iter(testdata.iter().copied().map(|x| self.alloc(x)))
        }
    }

    impl<T, const N: usize> LilVec<T, N>
    where
        T: fmt::Debug,
    {
        fn assert_is_array(&self) {
            assert_matches!(self, Self::Array(_));
        }

        fn assert_is_vec(&self) {
            assert_matches!(self, Self::Vec(_));
        }
    }

    impl<'a, const N: usize> LilVec<Scoped<'a>, N> {
        fn assert(&self, expect: &[u8]) {
            assert_eq!(self.is_empty(), expect.is_empty());
            assert_eq!(self.len(), expect.len());
            assert_eq!(self.as_slice(), expect);
        }
    }

    #[test]
    fn reserve() {
        let alloc = Alloc::new();
        let mut lv = alloc.alloc_lil_vec::<10>(&[1, 2, 3]);
        lv.assert(&[1, 2, 3]);
        lv.assert_is_array();
        assert_eq!(lv.capacity(), 10);
        alloc.assert(0);

        for _ in 0..3 {
            lv.reserve(7);
            lv.assert(&[1, 2, 3]);
            lv.assert_is_array();
            assert_eq!(lv.capacity(), 10);
            alloc.assert(0);
        }

        lv.reserve(8);
        lv.assert(&[1, 2, 3]);
        lv.assert_is_vec();
        assert!(lv.capacity() >= 11);
        alloc.assert(0);

        lv.reserve(100);
        lv.assert(&[1, 2, 3]);
        lv.assert_is_vec();
        assert!(lv.capacity() >= 100);
        alloc.assert(0);

        drop(lv);
        alloc.assert(3);
    }

    #[test]
    fn with_capacity() {
        <LilVec<u8, 3>>::with_capacity(3).assert_is_array();
        <LilVec<u8, 3>>::with_capacity(4).assert_is_vec();
    }

    #[test]
    fn realloc() {
        let alloc = Alloc::new();
        let lv = alloc.alloc_lil_vec::<2>(&[1, 2]);
        lv.assert(&[1, 2]);
        lv.assert_is_array();
        alloc.assert(0);

        let lv = lv.realloc::<3>();
        lv.assert(&[1, 2]);
        lv.assert_is_array();
        alloc.assert(0);

        let lv = lv.realloc::<2>();
        lv.assert(&[1, 2]);
        lv.assert_is_array();
        alloc.assert(0);

        let lv = lv.realloc::<1>();
        lv.assert(&[1, 2]);
        lv.assert_is_vec();
        assert!(lv.capacity() >= 2);
        alloc.assert(0);

        drop(lv);
        alloc.assert(2);
    }

    #[test]
    fn move_to_vec() {
        // array
        {
            let alloc = Alloc::new();
            let mut lv = alloc.alloc_lil_vec::<3>(&[1, 2]);
            lv.assert(&[1, 2]);
            lv.assert_is_array();
            alloc.assert(0);

            let vec = Vec::from(&mut lv);
            assert_eq!(vec, &[1, 2]);
            lv.assert(&[]);
            lv.assert_is_array();
            alloc.assert(0);

            drop(lv);
            alloc.assert(0);

            drop(vec);
            alloc.assert(2);
        }

        // vec
        {
            let alloc = Alloc::new();
            let mut lv = alloc.alloc_lil_vec::<0>(&[1, 2]);
            lv.assert(&[1, 2]);
            lv.assert_is_vec();
            alloc.assert(0);

            let vec = Vec::from(&mut lv);
            assert_eq!(vec, &[1, 2]);
            lv.assert(&[]);
            lv.assert_is_vec();
            alloc.assert(0);

            drop(lv);
            alloc.assert(0);

            drop(vec);
            alloc.assert(2);
        }
    }

    #[test]
    fn append() {
        // array/array
        {
            let alloc = Alloc::new();
            let mut lv1 = alloc.alloc_lil_vec::<4>(&[1, 2]);
            let mut lv2 = alloc.alloc_lil_vec::<1>(&[3]);
            lv1.assert(&[1, 2]);
            lv1.assert_is_array();
            lv2.assert(&[3]);
            lv2.assert_is_array();
            alloc.assert(0);

            lv1.append(&mut lv2);
            lv1.assert(&[1, 2, 3]);
            lv1.assert_is_array();
            lv2.assert(&[]);
            lv2.assert_is_array();
            alloc.assert(0);

            drop(lv2);
            alloc.assert(0);
            drop(lv1);
            alloc.assert(3);
        }

        // array/array promote to vec
        {
            let alloc = Alloc::new();
            let mut lv1 = alloc.alloc_lil_vec::<4>(&[1, 2]);
            let mut lv2 = alloc.alloc_lil_vec::<3>(&[3, 4, 5]);
            lv1.assert(&[1, 2]);
            lv1.assert_is_array();
            lv2.assert(&[3, 4, 5]);
            lv2.assert_is_array();
            alloc.assert(0);

            lv1.append(&mut lv2);
            lv1.assert(&[1, 2, 3, 4, 5]);
            lv1.assert_is_vec();
            lv2.assert(&[]);
            lv2.assert_is_array();
            alloc.assert(0);

            drop(lv2);
            alloc.assert(0);
            drop(lv1);
            alloc.assert(5);
        }

        // array/vec
        {
            let alloc = Alloc::new();
            let mut lv1 = alloc.alloc_lil_vec::<4>(&[1, 2]);
            let mut lv2 = alloc.alloc_lil_vec::<0>(&[3]);
            lv1.assert(&[1, 2]);
            lv1.assert_is_array();
            lv2.assert(&[3]);
            lv2.assert_is_vec();
            alloc.assert(0);

            lv1.append(&mut lv2);
            lv1.assert(&[1, 2, 3]);
            lv1.assert_is_array();
            lv2.assert(&[]);
            lv2.assert_is_vec();
            alloc.assert(0);

            drop(lv2);
            alloc.assert(0);
            drop(lv1);
            alloc.assert(3);
        }

        // array/vec promote to vec
        {
            let alloc = Alloc::new();
            let mut lv1 = alloc.alloc_lil_vec::<4>(&[1, 2]);
            let mut lv2 = alloc.alloc_lil_vec::<0>(&[3, 4, 5]);
            lv1.assert(&[1, 2]);
            lv1.assert_is_array();
            lv2.assert(&[3, 4, 5]);
            lv2.assert_is_vec();
            alloc.assert(0);

            lv1.append(&mut lv2);
            lv1.assert(&[1, 2, 3, 4, 5]);
            lv1.assert_is_vec();
            lv2.assert(&[]);
            lv2.assert_is_vec();
            alloc.assert(0);

            drop(lv2);
            alloc.assert(0);
            drop(lv1);
            alloc.assert(5);
        }

        // vec/array
        {
            let alloc = Alloc::new();
            let mut lv1 = alloc.alloc_lil_vec::<0>(&[1, 2]);
            let mut lv2 = alloc.alloc_lil_vec::<1>(&[3]);
            lv1.assert(&[1, 2]);
            lv1.assert_is_vec();
            lv2.assert(&[3]);
            lv2.assert_is_array();
            alloc.assert(0);

            lv1.append(&mut lv2);
            lv1.assert(&[1, 2, 3]);
            lv1.assert_is_vec();
            lv2.assert(&[]);
            lv2.assert_is_array();
            alloc.assert(0);

            drop(lv2);
            alloc.assert(0);
            drop(lv1);
            alloc.assert(3);
        }

        // vec/vec
        {
            let alloc = Alloc::new();
            let mut lv1 = alloc.alloc_lil_vec::<0>(&[1, 2]);
            let mut lv2 = alloc.alloc_lil_vec::<0>(&[3]);
            lv1.assert(&[1, 2]);
            lv1.assert_is_vec();
            lv2.assert(&[3]);
            lv2.assert_is_vec();
            alloc.assert(0);

            lv1.append(&mut lv2);
            lv1.assert(&[1, 2, 3]);
            lv1.assert_is_vec();
            lv2.assert(&[]);
            lv2.assert_is_vec();
            alloc.assert(0);

            drop(lv2);
            alloc.assert(0);
            drop(lv1);
            alloc.assert(3);
        }
    }

    #[test]
    fn append_vec() {
        // array
        {
            let alloc = Alloc::new();
            let mut lv = alloc.alloc_lil_vec::<4>(&[1, 2]);
            let mut vec = vec![alloc.alloc(3)];
            lv.assert(&[1, 2]);
            lv.assert_is_array();
            assert_eq!(vec, &[3]);
            alloc.assert(0);

            lv.append_vec(&mut vec);
            lv.assert(&[1, 2, 3]);
            lv.assert_is_array();
            assert_eq!(vec, &[]);
            alloc.assert(0);

            drop(vec);
            alloc.assert(0);
            drop(lv);
            alloc.assert(3);
        }

        // array promote to vec
        {
            let alloc = Alloc::new();
            let mut lv = alloc.alloc_lil_vec::<2>(&[1, 2]);
            let mut vec = vec![alloc.alloc(3)];
            lv.assert(&[1, 2]);
            lv.assert_is_array();
            assert_eq!(vec, &[3]);
            alloc.assert(0);

            lv.append_vec(&mut vec);
            lv.assert(&[1, 2, 3]);
            lv.assert_is_vec();
            assert_eq!(vec, &[]);
            alloc.assert(0);

            drop(vec);
            alloc.assert(0);
            drop(lv);
            alloc.assert(3);
        }

        // vec
        {
            let alloc = Alloc::new();
            let mut lv = alloc.alloc_lil_vec::<0>(&[1, 2]);
            let mut vec = vec![alloc.alloc(3)];
            lv.assert(&[1, 2]);
            lv.assert_is_vec();
            assert_eq!(vec, &[3]);
            alloc.assert(0);

            lv.append_vec(&mut vec);
            lv.assert(&[1, 2, 3]);
            lv.assert_is_vec();
            assert_eq!(vec, &[]);
            alloc.assert(0);

            drop(vec);
            alloc.assert(0);
            drop(lv);
            alloc.assert(3);
        }
    }

    #[test]
    fn append_to_vec() {
        // array
        {
            let alloc = Alloc::new();
            let mut lv = alloc.alloc_lil_vec::<3>(&[1, 2]);
            let mut vec = vec![alloc.alloc(3)];
            lv.assert(&[1, 2]);
            lv.assert_is_array();
            assert_eq!(vec, &[3]);
            alloc.assert(0);

            lv.append_to_vec(&mut vec);
            lv.assert(&[]);
            lv.assert_is_array();
            assert_eq!(vec, &[3, 1, 2]);
            alloc.assert(0);

            drop(lv);
            alloc.assert(0);
            drop(vec);
            alloc.assert(3);
        }

        // vec
        {
            let alloc = Alloc::new();
            let mut lv = alloc.alloc_lil_vec::<0>(&[1, 2]);
            let mut vec = vec![alloc.alloc(3)];
            lv.assert(&[1, 2]);
            lv.assert_is_vec();
            assert_eq!(vec, &[3]);
            alloc.assert(0);

            lv.append_to_vec(&mut vec);
            lv.assert(&[]);
            lv.assert_is_vec();
            assert_eq!(vec, &[3, 1, 2]);
            alloc.assert(0);

            drop(lv);
            alloc.assert(0);
            drop(vec);
            alloc.assert(3);
        }
    }

    #[test]
    fn insert_array_promote_vec() {
        let alloc = Alloc::new();
        let mut lv = alloc.alloc_lil_vec::<3>(&[1, 2]);
        lv.assert(&[1, 2]);
        lv.assert_is_array();
        alloc.assert(0);

        lv.insert(0, alloc.alloc(3));
        lv.assert(&[3, 1, 2]);
        lv.assert_is_array();
        alloc.assert(0);

        lv.insert(2, alloc.alloc(4));
        lv.assert(&[3, 1, 4, 2]);
        lv.assert_is_vec();
        alloc.assert(0);

        drop(lv);
        alloc.assert(4);
    }

    #[test]
    fn push_array_promote_vec() {
        let alloc = Alloc::new();
        let mut lv = alloc.alloc_lil_vec::<2>(&[1]);
        lv.assert(&[1]);
        lv.assert_is_array();
        alloc.assert(0);

        lv.push(alloc.alloc(2));
        lv.assert(&[1, 2]);
        lv.assert_is_array();
        alloc.assert(0);

        lv.push(alloc.alloc(3));
        lv.assert(&[1, 2, 3]);
        lv.assert_is_vec();
        alloc.assert(0);

        drop(lv);
        alloc.assert(3);
    }
}
