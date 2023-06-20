pub trait SliceExt {
    fn find(&self, pattern: &Self) -> Option<usize>;
}

impl<T> SliceExt for [T]
where
    T: PartialEq,
{
    fn find(&self, pattern: &Self) -> Option<usize> {
        if pattern.is_empty() {
            return Some(0);
        }
        self.windows(pattern.len())
            .position(|slice| slice == pattern)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn slice() {
        let x = [0, 1, 2, 3, 4].as_slice();
        assert_eq!(x.find([].as_slice()), Some(0));
        assert_eq!(x.find([0, 1].as_slice()), Some(0));
        assert_eq!(x.find([1, 2, 3].as_slice()), Some(1));
        assert_eq!(x.find([3, 4].as_slice()), Some(3));

        assert_eq!(x.find([3, 2].as_slice()), None);
        assert_eq!(x.find([4, 5].as_slice()), None);
        assert_eq!(x.find([5].as_slice()), None);

        let x: &[u8] = [].as_slice();
        assert_eq!(x.find([].as_slice()), Some(0));
        assert_eq!(x.find([1u8].as_slice()), None);
    }
}
