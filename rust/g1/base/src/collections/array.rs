use std::borrow::{Borrow, BorrowMut};
use std::cmp::Ordering;
use std::fmt;
use std::hash::{Hash, Hasher};
use std::iter::FusedIterator;
use std::mem::{self, MaybeUninit};
use std::ops::{Deref, DerefMut, Index, IndexMut, Range};
use std::ptr;
use std::slice::SliceIndex;

// Its interface is closer to `Vec<T>` than to `[T; N]`.  Should we name it `BoundedVec` rather
// than `Array`?
pub struct Array<T, const N: usize> {
    array: [MaybeUninit<T>; N],
    len: usize,
}

impl<T, const N: usize> Drop for Array<T, N> {
    fn drop(&mut self) {
        drop_in_place(&mut self.array[0..self.len]);
    }
}

impl<T, const N: usize> Array<T, N> {
    pub fn as_slice(&self) -> &[T] {
        unsafe { self.array[0..self.len].assume_init_ref() }
    }

    pub fn as_mut_slice(&mut self) -> &mut [T] {
        unsafe { self.array[0..self.len].assume_init_mut() }
    }

    pub fn as_ptr(&self) -> *const T {
        as_ptr(&self.array)
    }

    pub fn as_mut_ptr(&mut self) -> *mut T {
        as_mut_ptr(&mut self.array)
    }

    fn move_to(&mut self, dst: *mut T) -> usize {
        let len = mem::take(&mut self.len);
        unsafe { ptr::copy_nonoverlapping(self.as_ptr(), dst, len) };
        len
    }

    // NOTE: It is your responsibility to ensure that `self.len` is updated after the call.
    fn copy_within(&mut self, src: Range<usize>, dst: usize) {
        let count = src.end - src.start;
        let src = src.start;
        debug_assert!(dst + count <= N);
        let ptr = self.as_mut_ptr();
        unsafe { ptr::copy(ptr.add(src), ptr.add(dst), count) }
    }
}

fn as_ptr<T, const N: usize>(array: &[MaybeUninit<T>; N]) -> *const T {
    MaybeUninit::slice_as_ptr(array.as_slice())
}

fn as_mut_ptr<T, const N: usize>(array: &mut [MaybeUninit<T>; N]) -> *mut T {
    MaybeUninit::slice_as_mut_ptr(array.as_mut_slice())
}

fn drop_in_place<T>(slice: &mut [MaybeUninit<T>]) {
    unsafe { slice.assume_init_drop() };
}

//
// Construct.
//

impl<T, const N: usize> Clone for Array<T, N>
where
    T: Clone,
{
    fn clone(&self) -> Self {
        let mut array = [const { MaybeUninit::uninit() }; N];
        array[0..self.len].write_clone_of_slice(self);
        Self {
            array,
            len: self.len,
        }
    }
}

impl<T, const N: usize> Default for Array<T, N> {
    fn default() -> Self {
        Self::new()
    }
}

impl<T, const N: usize> From<[T; N]> for Array<T, N> {
    fn from(array: [T; N]) -> Self {
        Self {
            array: MaybeUninit::new(array).transpose(),
            len: N,
        }
    }
}

impl<T, const N: usize> FromIterator<T> for Array<T, N> {
    fn from_iter<I>(iter: I) -> Self
    where
        I: IntoIterator<Item = T>,
    {
        let mut this = Self::new();
        this.extend(iter);
        this
    }
}

impl<T, const N: usize> Array<T, N> {
    pub fn new() -> Self {
        Self {
            array: [const { MaybeUninit::uninit() }; N],
            len: 0,
        }
    }
}

//
// Convert.
//

impl<T, const N: usize> From<Array<T, N>> for Vec<T> {
    fn from(mut other: Array<T, N>) -> Self {
        (&mut other).into()
    }
}

impl<T, const N: usize> Array<T, N> {
    pub fn realloc<const M: usize>(mut self) -> Result<Array<T, M>, Self> {
        if self.len > M {
            return Err(self);
        }

        let mut array = [const { MaybeUninit::uninit() }; M];
        let len = self.move_to(as_mut_ptr(&mut array));
        Ok(Array { array, len })
    }
}

//
// Move.
//

impl<'a, T, const N: usize> From<&'a mut Array<T, N>> for Vec<T> {
    fn from(other: &'a mut Array<T, N>) -> Self {
        let mut this = Self::with_capacity(other.len);
        other.append_to_vec(&mut this);
        this
    }
}

impl<T, const N: usize> Array<T, N> {
    pub fn append<const M: usize>(&mut self, other: &mut Array<T, M>) {
        assert!(self.try_append(other));
    }

    pub fn try_append<const M: usize>(&mut self, other: &mut Array<T, M>) -> bool {
        if self.len + other.len > N {
            return false;
        }

        self.len += other.move_to(unsafe { self.as_mut_ptr().add(self.len) });
        true
    }

    pub fn append_vec(&mut self, other: &mut Vec<T>) {
        assert!(self.try_append_vec(other));
    }

    pub fn try_append_vec(&mut self, other: &mut Vec<T>) -> bool {
        let other_len = other.len();
        if self.len + other_len > N {
            return false;
        }

        unsafe {
            ptr::copy_nonoverlapping(other.as_ptr(), self.as_mut_ptr().add(self.len), other_len);
            self.len += other_len;
            other.set_len(0);
        }
        true
    }

    pub fn append_to_vec(&mut self, other: &mut Vec<T>) {
        let other_len = other.len();
        other.reserve(self.len());
        unsafe {
            let len = self.move_to(other.as_mut_ptr().add(other_len));
            other.set_len(other_len + len);
        }
    }
}

//
// Iterate.
//

#[derive(Debug)]
pub struct IntoIter<T, const N: usize> {
    array: Array<T, N>,
    range: Range<usize>,
}

impl<T, const N: usize> Drop for IntoIter<T, N> {
    fn drop(&mut self) {
        drop_in_place(&mut self.array.array[self.range.clone()]);
    }
}

impl<T, const N: usize> IntoIterator for Array<T, N> {
    type Item = T;
    type IntoIter = IntoIter<T, N>;

    fn into_iter(self) -> Self::IntoIter {
        IntoIter::new(self)
    }
}

impl<T, const N: usize> IntoIter<T, N> {
    fn new(mut array: Array<T, N>) -> Self {
        let range = 0..array.len;
        array.len = 0; // The responsibility of dropping elements is transferred to `IntoIter`.
        Self { array, range }
    }

    // NOTE: It is your responsibility to ensure that each element is read at most once.
    fn read(&self, i: usize) -> T {
        unsafe { self.array.array[i].assume_init_read() }
    }
}

impl<T, const N: usize> Iterator for IntoIter<T, N> {
    type Item = T;

    fn next(&mut self) -> Option<Self::Item> {
        self.range.next().map(|i| self.read(i))
    }

    fn size_hint(&self) -> (usize, Option<usize>) {
        self.range.size_hint()
    }

    fn count(self) -> usize {
        self.range.end - self.range.start
    }

    fn nth(&mut self, n: usize) -> Option<Self::Item> {
        let Range { start, end } = self.range.clone();
        let i = self.range.nth(n);
        drop_in_place(&mut self.array.array[start..i.unwrap_or(end)]);
        i.map(|i| self.read(i))
    }

    fn last(mut self) -> Option<Self::Item> {
        self.next_back()
    }
}

impl<T, const N: usize> DoubleEndedIterator for IntoIter<T, N> {
    fn next_back(&mut self) -> Option<Self::Item> {
        self.range.next_back().map(|i| self.read(i))
    }

    fn nth_back(&mut self, n: usize) -> Option<Self::Item> {
        let Range { start, end } = self.range.clone();
        let i = self.range.nth_back(n);
        drop_in_place(&mut self.array.array[i.map_or(start, |i| i + 1)..end]);
        i.map(|i| self.read(i))
    }
}

impl<T, const N: usize> ExactSizeIterator for IntoIter<T, N> {}

impl<T, const N: usize> FusedIterator for IntoIter<T, N> {}

//
// Read.
//

impl<T, const N: usize> fmt::Debug for Array<T, N>
where
    T: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> Result<(), fmt::Error> {
        fmt::Debug::fmt(&**self, f)
    }
}

impl<T: Eq, const N: usize> Eq for Array<T, N> {}

impl<T, U, const N: usize> PartialEq<Array<U, N>> for Array<T, N>
where
    T: PartialEq<U>,
{
    fn eq(&self, other: &Array<U, N>) -> bool {
        self[..] == other[..]
    }
}

impl<T, const N: usize> Ord for Array<T, N>
where
    T: Ord,
{
    fn cmp(&self, other: &Self) -> Ordering {
        Ord::cmp(&**self, &**other)
    }
}

impl<T, const N: usize> PartialOrd for Array<T, N>
where
    T: PartialOrd,
{
    fn partial_cmp(&self, other: &Array<T, N>) -> Option<Ordering> {
        PartialOrd::partial_cmp(&**self, &**other)
    }
}

impl<T, const N: usize> Hash for Array<T, N>
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

impl<T, const N: usize> Array<T, N> {
    pub fn is_empty(&self) -> bool {
        self.len == 0
    }

    pub fn is_full(&self) -> bool {
        self.len == N
    }

    pub fn len(&self) -> usize {
        self.len
    }
}

//
// AsRef/Borrow/Deref.
//

impl<T, const N: usize> Deref for Array<T, N> {
    type Target = [T];

    fn deref(&self) -> &Self::Target {
        self.as_slice()
    }
}

impl<T, const N: usize> DerefMut for Array<T, N> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        self.as_mut_slice()
    }
}

impl<T, const N: usize> AsRef<[T]> for Array<T, N> {
    fn as_ref(&self) -> &[T] {
        self
    }
}

impl<T, const N: usize> AsMut<[T]> for Array<T, N> {
    fn as_mut(&mut self) -> &mut [T] {
        self
    }
}

impl<T, const N: usize> Borrow<[T]> for Array<T, N> {
    fn borrow(&self) -> &[T] {
        self
    }
}

impl<T, const N: usize> BorrowMut<[T]> for Array<T, N> {
    fn borrow_mut(&mut self) -> &mut [T] {
        self
    }
}

//
// Index.
//

impl<T, I, const N: usize> Index<I> for Array<T, N>
where
    I: SliceIndex<[T]>,
{
    type Output = I::Output;

    fn index(&self, index: I) -> &Self::Output {
        Index::index(&**self, index)
    }
}

impl<T, I, const N: usize> IndexMut<I> for Array<T, N>
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

impl<T, const N: usize> Extend<T> for Array<T, N> {
    fn extend<I>(&mut self, iter: I)
    where
        I: IntoIterator<Item = T>,
    {
        // TODO: Optimize this the way the stdlib does?
        for value in iter {
            // TODO: I am not sure what the right action is when the array is full.  At the moment,
            // I just ignore the rest of the values.
            if self.try_push(value).is_err() {
                break;
            }
        }
    }
}

impl<T, const N: usize> Array<T, N> {
    pub fn clear(&mut self) {
        drop_in_place(&mut self.array[0..mem::take(&mut self.len)]);
    }

    pub fn insert(&mut self, index: usize, element: T) {
        assert!(self.try_insert(index, element).is_ok());
    }

    pub fn try_insert(&mut self, index: usize, element: T) -> Result<(), T> {
        assert!(index <= self.len);

        if self.len == N {
            return Err(element);
        }

        if index < self.len {
            self.copy_within(index..self.len, index + 1);
        }
        self.array[index].write(element);
        self.len += 1;
        Ok(())
    }

    pub fn push(&mut self, value: T) {
        assert!(self.try_push(value).is_ok());
    }

    pub fn try_push(&mut self, value: T) -> Result<(), T> {
        self.try_insert(self.len, value)
    }

    pub fn remove(&mut self, index: usize) -> T {
        assert!(index < self.len);

        let element = unsafe { self.array[index].assume_init_read() };
        self.copy_within(index + 1..self.len, index);
        self.len -= 1;
        element
    }

    pub fn pop(&mut self) -> Option<T> {
        (self.len > 0).then(|| {
            self.len -= 1;
            unsafe { self.array[self.len].assume_init_read() }
        })
    }
}

#[cfg(test)]
pub(super) mod test_harness {
    use std::sync::atomic::{AtomicUsize, Ordering};

    use super::*;

    pub(in super::super) struct Alloc {
        num_dropped: AtomicUsize,
    }

    #[derive(Clone, Debug)]
    pub(in super::super) struct Scoped<'a> {
        pub(in super::super) n: u8,
        num_dropped: &'a AtomicUsize,
    }

    impl Drop for Scoped<'_> {
        fn drop(&mut self) {
            self.num_dropped.fetch_add(1, Ordering::SeqCst);
        }
    }

    impl PartialEq<u8> for Scoped<'_> {
        fn eq(&self, other: &u8) -> bool {
            self.n == *other
        }
    }

    impl Alloc {
        pub(in super::super) fn new() -> Self {
            Self {
                num_dropped: AtomicUsize::new(0),
            }
        }

        pub(in super::super) fn alloc_array<const N: usize>(
            &self,
            testdata: &[u8],
        ) -> Array<Scoped, N> {
            Array::from_iter(testdata.iter().copied().map(|x| self.alloc(x)))
        }

        pub(in super::super) fn alloc(&self, n: u8) -> Scoped {
            Scoped {
                n,
                num_dropped: &self.num_dropped,
            }
        }

        pub(in super::super) fn assert(&self, expect: usize) {
            assert_eq!(self.num_dropped(), expect);
        }

        pub(in super::super) fn num_dropped(&self) -> usize {
            self.num_dropped.load(Ordering::SeqCst)
        }
    }

    impl<'a, const N: usize> Array<Scoped<'a>, N> {
        pub(in super::super) fn assert(&self, expect: &[u8]) {
            assert_eq!(self.is_empty(), expect.is_empty());
            assert_eq!(self.is_full(), expect.len() == N);
            assert_eq!(self.len(), expect.len());
            assert_eq!(self.as_slice(), expect);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::test_harness::*;
    use super::*;

    #[test]
    fn array_drop() {
        {
            let alloc = Alloc::new();
            let array = alloc.alloc_array::<3>(&[1, 2, 3]);
            array.assert(&[1, 2, 3]);
            alloc.assert(0);

            drop(array);
            alloc.assert(3);
        }

        {
            let alloc = Alloc::new();
            let array = alloc.alloc_array::<3>(&[1, 2]);
            array.assert(&[1, 2]);
            alloc.assert(0);

            drop(array);
            alloc.assert(2);
        }
    }

    #[test]
    fn as_slice() {
        let alloc = Alloc::new();
        let mut array = alloc.alloc_array::<3>(&[]);
        array.assert(&[]);
        assert_eq!(array.as_mut_slice(), &[]);

        array.push(alloc.alloc(1));
        array.assert(&[1]);
        assert_eq!(array.as_mut_slice(), &[1]);

        array.push(alloc.alloc(2));
        array.assert(&[1, 2]);
        assert_eq!(array.as_mut_slice(), &[1, 2]);
    }

    #[test]
    fn clone() {
        let alloc = Alloc::new();
        let a1 = alloc.alloc_array::<3>(&[1, 2]);
        let a2 = a1.clone();
        a1.assert(&[1, 2]);
        a2.assert(&[1, 2]);
        alloc.assert(0);

        drop(a1);
        alloc.assert(2);

        drop(a2);
        alloc.assert(4);
    }

    #[test]
    fn from_array() {
        {
            let array = Array::from([]);
            array.assert(&[]);
        }

        {
            let alloc = Alloc::new();
            let array = Array::from([alloc.alloc(1), alloc.alloc(2), alloc.alloc(3)]);
            array.assert(&[1, 2, 3]);
            alloc.assert(0);

            drop(array);
            alloc.assert(3);
        }
    }

    #[test]
    fn from_iter() {
        {
            let array = <Array<Scoped, 4>>::from_iter([].into_iter());
            array.assert(&[]);
        }

        {
            let alloc = Alloc::new();
            let array = <Array<Scoped, 4>>::from_iter(
                [alloc.alloc(1), alloc.alloc(2), alloc.alloc(3)].into_iter(),
            );
            array.assert(&[1, 2, 3]);
            alloc.assert(0);

            drop(array);
            alloc.assert(3);
        }
    }

    #[test]
    fn array_new() {
        let alloc = Alloc::new();
        let mut array = <Array<Scoped, 3>>::new();
        array.assert(&[]);

        array.push(alloc.alloc(1));
        array.assert(&[1]);
        alloc.assert(0);

        array.push(alloc.alloc(2));
        array.assert(&[1, 2]);
        alloc.assert(0);

        drop(array);
        alloc.assert(2);
    }

    #[test]
    fn into_vec() {
        let alloc = Alloc::new();
        let array = alloc.alloc_array::<3>(&[1, 2]);
        array.assert(&[1, 2]);
        alloc.assert(0);

        let vec = Vec::from(array);
        assert_eq!(vec, &[1, 2]);
        alloc.assert(0);

        drop(vec);
        alloc.assert(2);
    }

    #[test]
    fn realloc() {
        {
            let alloc = Alloc::new();
            let array = alloc.alloc_array::<4>(&[1, 2]);
            array.assert(&[1, 2]);
            alloc.assert(0);

            let array = array.realloc::<3>().unwrap();
            array.assert(&[1, 2]);
            alloc.assert(0);

            drop(array);
            alloc.assert(2);
        }

        {
            let alloc = Alloc::new();
            let array = alloc.alloc_array::<4>(&[1, 2, 3]);
            array.assert(&[1, 2, 3]);
            alloc.assert(0);

            let array = array.realloc::<2>().unwrap_err();
            array.assert(&[1, 2, 3]);
            alloc.assert(0);

            drop(array);
            alloc.assert(3);
        }
    }

    #[test]
    fn move_to_vec() {
        let alloc = Alloc::new();
        let mut array = alloc.alloc_array::<3>(&[1, 2]);
        array.assert(&[1, 2]);
        alloc.assert(0);

        let vec = Vec::from(&mut array);
        assert_eq!(vec, &[1, 2]);
        array.assert(&[]);
        alloc.assert(0);

        drop(array);
        alloc.assert(0);

        drop(vec);
        alloc.assert(2);
    }

    #[test]
    fn try_append() {
        {
            let alloc = Alloc::new();
            let mut a1 = alloc.alloc_array::<3>(&[1, 2]);
            let mut a2 = alloc.alloc_array::<3>(&[3]);
            a1.assert(&[1, 2]);
            a2.assert(&[3]);
            alloc.assert(0);

            assert_eq!(a1.try_append(&mut a2), true);
            a1.assert(&[1, 2, 3]);
            a2.assert(&[]);
            alloc.assert(0);

            drop(a2);
            alloc.assert(0);
            drop(a1);
            alloc.assert(3);
        }

        {
            let alloc = Alloc::new();
            let mut a1 = alloc.alloc_array::<3>(&[1, 2]);
            let mut a2 = alloc.alloc_array::<3>(&[3, 4]);
            a1.assert(&[1, 2]);
            a2.assert(&[3, 4]);
            alloc.assert(0);

            assert_eq!(a1.try_append(&mut a2), false);
            a1.assert(&[1, 2]);
            a2.assert(&[3, 4]);
            alloc.assert(0);

            drop(a1);
            alloc.assert(2);
            drop(a2);
            alloc.assert(4);
        }
    }

    #[test]
    fn try_append_vec() {
        {
            let alloc = Alloc::new();
            let mut array = alloc.alloc_array::<4>(&[1, 2]);
            let mut vec = vec![alloc.alloc(3)];
            array.assert(&[1, 2]);
            assert_eq!(vec, &[3]);
            alloc.assert(0);

            assert_eq!(array.try_append_vec(&mut vec), true);
            array.assert(&[1, 2, 3]);
            assert_eq!(vec, &[]);
            alloc.assert(0);

            drop(vec);
            alloc.assert(0);
            drop(array);
            alloc.assert(3);
        }

        {
            let alloc = Alloc::new();
            let mut array = alloc.alloc_array::<3>(&[1, 2]);
            let mut vec = vec![alloc.alloc(3), alloc.alloc(4)];
            array.assert(&[1, 2]);
            assert_eq!(vec, &[3, 4]);
            alloc.assert(0);

            assert_eq!(array.try_append_vec(&mut vec), false);
            array.assert(&[1, 2]);
            assert_eq!(vec, &[3, 4]);
            alloc.assert(0);

            drop(vec);
            alloc.assert(2);
            drop(array);
            alloc.assert(4);
        }
    }

    #[test]
    fn append_to_vec() {
        let alloc = Alloc::new();
        let mut array = alloc.alloc_array::<3>(&[1, 2]);
        let mut vec = vec![alloc.alloc(3)];
        array.assert(&[1, 2]);
        assert_eq!(vec, &[3]);
        alloc.assert(0);

        array.append_to_vec(&mut vec);
        array.assert(&[]);
        assert_eq!(vec, &[3, 1, 2]);
        alloc.assert(0);

        drop(array);
        alloc.assert(0);
        drop(vec);
        alloc.assert(3);
    }

    #[test]
    fn into_iter() {
        // next/next_back
        {
            let alloc = Alloc::new();
            let array = alloc.alloc_array::<5>(&[1, 2, 3, 4]);
            array.assert(&[1, 2, 3, 4]);
            alloc.assert(0);

            let mut iter = array.into_iter();
            alloc.assert(0);

            {
                let item = iter.next().unwrap();
                alloc.assert(0);
                assert_eq!(item, 1);
            }
            alloc.assert(1);

            {
                let item = iter.next_back().unwrap();
                alloc.assert(1);
                assert_eq!(item, 4);
            }
            alloc.assert(2);

            {
                let item = iter.next().unwrap();
                alloc.assert(2);
                assert_eq!(item, 2);
            }
            alloc.assert(3);

            {
                let item = iter.next_back().unwrap();
                alloc.assert(3);
                assert_eq!(item, 3);
            }
            alloc.assert(4);

            for _ in 0..3 {
                assert!(iter.next().is_none());
                assert!(iter.next_back().is_none());
                alloc.assert(4);
            }
        }

        // nth
        {
            let alloc = Alloc::new();
            let array = alloc.alloc_array::<6>(&[1, 2, 3, 4, 5]);
            array.assert(&[1, 2, 3, 4, 5]);
            alloc.assert(0);

            let mut iter = array.into_iter();
            alloc.assert(0);

            {
                let item = iter.nth(1).unwrap();
                alloc.assert(1);
                assert_eq!(item, 2);
            }
            alloc.assert(2);

            {
                let item = iter.nth(1).unwrap();
                alloc.assert(3);
                assert_eq!(item, 4);
            }
            alloc.assert(4);

            for _ in 0..3 {
                let item = iter.nth(2);
                alloc.assert(5);
                assert!(item.is_none());
            }
        }

        // nth_back
        {
            let alloc = Alloc::new();
            let array = alloc.alloc_array::<6>(&[1, 2, 3, 4, 5]);
            array.assert(&[1, 2, 3, 4, 5]);
            alloc.assert(0);

            let mut iter = array.into_iter();
            alloc.assert(0);

            {
                let item = iter.nth_back(1).unwrap();
                alloc.assert(1);
                assert_eq!(item, 4);
            }
            alloc.assert(2);

            {
                let item = iter.nth_back(1).unwrap();
                alloc.assert(3);
                assert_eq!(item, 2);
            }
            alloc.assert(4);

            for _ in 0..3 {
                let item = iter.nth_back(2);
                alloc.assert(5);
                assert!(item.is_none());
            }
        }

        // drop
        {
            let alloc = Alloc::new();
            let array = alloc.alloc_array::<3>(&[1, 2]);
            array.assert(&[1, 2]);
            alloc.assert(0);

            let iter = array.into_iter();
            alloc.assert(0);

            drop(iter);
            alloc.assert(2);
        }
    }

    #[test]
    fn eq_cmp_hash() {
        use std::hash::DefaultHasher;

        fn hash<T: Hash>(value: &T) -> u64 {
            let mut state = DefaultHasher::new();
            value.hash(&mut state);
            state.finish()
        }

        let a0 = <Array<u8, 0>>::from([]);
        let a1 = Array::from([1]);
        let a2 = Array::from([1, 2]);
        let a3 = Array::from([1, 2, 3]);

        let b1 = Array::from([2]);
        let b2 = Array::from([2, 1]);
        let b3 = Array::from([1, 3, 2]);

        assert_eq!(a0, a0);
        assert_eq!(a1, a1);
        assert_eq!(a2, a2);
        assert_eq!(a3, a3);

        assert_ne!(a1, b1);
        assert_ne!(a2, b2);
        assert_ne!(a3, b3);

        assert!(a1 < b1);
        assert!(a2 < b2);
        assert!(a3 < b3);

        assert_eq!(hash(&a0), hash::<[u8; 0]>(&[]));
        assert_eq!(hash(&a1), hash(&[1]));
        assert_eq!(hash(&a2), hash(&[1, 2]));
        assert_eq!(hash(&a3), hash(&[1, 2, 3]));

        assert_eq!(hash(&b1), hash(&[2]));
        assert_eq!(hash(&b2), hash(&[2, 1]));
        assert_eq!(hash(&b3), hash(&[1, 3, 2]));
    }

    #[test]
    fn index() {
        let alloc = Alloc::new();
        let mut array = alloc.alloc_array::<3>(&[1, 2]);
        array.assert(&[1, 2]);

        assert_eq!(&array[0], &1);
        assert_eq!(&array[1], &2);

        array[0].n = 3;
        array[1].n = 4;

        assert_eq!(&array[0], &3);
        assert_eq!(&array[1], &4);

        alloc.assert(0);
    }

    #[test]
    #[should_panic(expected = "index out of bounds: the len is 1 but the index is 1")]
    fn index_panic() {
        let array = Array::from([1]);
        array[1];
    }

    #[test]
    fn extend() {
        {
            let alloc = Alloc::new();
            let mut array = <Array<Scoped, 3>>::new();
            array.extend((1..=2).map(|x| alloc.alloc(x)));
            array.assert(&[1, 2]);
            alloc.assert(0);

            drop(array);
            alloc.assert(2);
        }

        {
            let alloc = Alloc::new();
            let mut array = <Array<Scoped, 3>>::new();
            array.extend((1..=100).map(|x| alloc.alloc(x)));
            array.assert(&[1, 2, 3]);
            alloc.assert(1); // `Array::extend` does not consume the entire iterator.

            drop(array);
            alloc.assert(4);
        }
    }

    #[test]
    fn clear() {
        let alloc = Alloc::new();
        let mut array = alloc.alloc_array::<3>(&[1, 2]);
        array.assert(&[1, 2]);
        alloc.assert(0);

        for _ in 0..3 {
            array.clear();
            array.assert(&[]);
            alloc.assert(2);
        }

        drop(array);
        alloc.assert(2);
    }

    #[test]
    fn try_insert() {
        let alloc = Alloc::new();
        let mut array = <Array<Scoped, 4>>::new();
        array.assert(&[]);
        alloc.assert(0);

        assert!(array.try_insert(0, alloc.alloc(10)).is_ok());
        array.assert(&[10]);
        alloc.assert(0);

        assert!(array.try_insert(0, alloc.alloc(11)).is_ok());
        array.assert(&[11, 10]);
        alloc.assert(0);

        assert!(array.try_insert(1, alloc.alloc(12)).is_ok());
        array.assert(&[11, 12, 10]);
        alloc.assert(0);

        assert!(array.try_insert(3, alloc.alloc(13)).is_ok());
        array.assert(&[11, 12, 10, 13]);
        alloc.assert(0);

        assert_eq!(array.try_insert(0, alloc.alloc(14)).unwrap_err(), 14);
        array.assert(&[11, 12, 10, 13]);
        alloc.assert(1);

        drop(array);
        alloc.assert(5);
    }

    #[test]
    fn remove() {
        let alloc = Alloc::new();
        let mut array = alloc.alloc_array::<4>(&[1, 2, 3]);
        array.assert(&[1, 2, 3]);
        alloc.assert(0);

        {
            let item = array.remove(0);
            assert_eq!(item, 1);
            array.assert(&[2, 3]);
            alloc.assert(0);
        }
        alloc.assert(1);

        {
            let item = array.remove(1);
            assert_eq!(item, 3);
            array.assert(&[2]);
            alloc.assert(1);
        }
        alloc.assert(2);
    }

    #[test]
    fn pop() {
        let alloc = Alloc::new();
        let mut array = alloc.alloc_array::<3>(&[1, 2]);
        array.assert(&[1, 2]);
        alloc.assert(0);

        {
            let item = array.pop().unwrap();
            assert_eq!(item, 2);
            array.assert(&[1]);
            alloc.assert(0);
        }
        alloc.assert(1);

        {
            let item = array.pop().unwrap();
            assert_eq!(item, 1);
            array.assert(&[]);
            alloc.assert(1);
        }
        alloc.assert(2);

        for _ in 0..3 {
            assert!(array.pop().is_none());
            array.assert(&[]);
            alloc.assert(2);
        }
    }
}
