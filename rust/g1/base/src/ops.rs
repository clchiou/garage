use std::borrow::Borrow;
use std::iter;
use std::ops::{Bound, RangeBounds, Residual, Try};

pub use g1_base_derive::{Deref, DerefMut};

// Sometimes we need to work around `Deref` not being reflexive.
#[derive(Clone, Debug, Deref)]
pub struct AsDeref<T>(pub T);

// Ditto.
#[derive(Clone, Debug, Deref, DerefMut)]
pub struct AsDerefMut<T>(pub T);

/// Implements compound assignment operators for slice types.
pub struct SliceCompoundAssignOp<'a, T>(pub &'a mut [T]);

macro_rules! gen_impl {
    ($trait:ident, $func:ident) => {
        impl<'a, T, Slice> std::ops::$trait<Slice> for SliceCompoundAssignOp<'a, T>
        where
            Slice: Borrow<[T]>,
            for<'b> T: std::ops::$trait<&'b T>,
        {
            fn $func(&mut self, rhs: Slice) {
                let slice = rhs.borrow();
                assert_eq!(self.0.len(), slice.len());
                self.0
                    .iter_mut()
                    .zip(slice.iter())
                    .for_each(|(lhs, rhs)| T::$func(lhs, rhs));
            }
        }
    };
}

gen_impl!(AddAssign, add_assign);
gen_impl!(BitAndAssign, bitand_assign);
gen_impl!(BitOrAssign, bitor_assign);
gen_impl!(BitXorAssign, bitxor_assign);
gen_impl!(DivAssign, div_assign);
gen_impl!(MulAssign, mul_assign);
gen_impl!(RemAssign, rem_assign);
gen_impl!(ShlAssign, shl_assign);
gen_impl!(ShrAssign, shr_assign);
gen_impl!(SubAssign, sub_assign);

pub trait BoundExt<T> {
    fn into_option(self) -> Option<T>;

    fn try_map<F, U, R>(self, f: F) -> <R as Residual<Bound<U>>>::TryType
    where
        F: FnOnce<(T,), Output: Try<Output = U, Residual = R>>,
        R: Residual<Bound<U>>;
}

impl<T> BoundExt<T> for Bound<T> {
    fn into_option(self) -> Option<T> {
        match self {
            Self::Included(x) | Self::Excluded(x) => Some(x),
            Self::Unbounded => None,
        }
    }

    fn try_map<F, U, R>(self, f: F) -> <R as Residual<Bound<U>>>::TryType
    where
        F: FnOnce<(T,), Output: Try<Output = U, Residual = R>>,
        R: Residual<Bound<U>>,
    {
        Try::from_output(match self {
            Self::Included(x) => Bound::Included(f(x)?),
            Self::Excluded(x) => Bound::Excluded(f(x)?),
            Self::Unbounded => Bound::Unbounded,
        })
    }
}

pub trait RangeBoundsExt<T>
where
    T: ?Sized,
{
    fn iter<'a>(&'a self) -> impl Iterator<Item = &'a T>
    where
        T: 'a;
}

impl<B, T> RangeBoundsExt<T> for B
where
    B: RangeBounds<T>,
    T: ?Sized,
{
    fn iter<'a>(&'a self) -> impl Iterator<Item = &'a T>
    where
        T: 'a,
    {
        iter::chain(
            self.start_bound().into_option(),
            self.end_bound().into_option(),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    macro_rules! eval {
        ($op:tt $x:expr, $y:expr) => {{
            let mut x = $x;
            let mut xs = SliceCompoundAssignOp(&mut x);
            xs $op $y;
            x
        }};
    }

    #[test]
    fn compound_assignment_operators() {
        assert_eq!(eval!(+= [1, 2, 3], [1, 2, 3]), [2, 4, 6]);
        assert_eq!(eval!(-= [3, 2, 1], [1, 2, 3]), [2, 0, -2]);
        assert_eq!(eval!(*= [1, 2, 3], [1, 2, 3]), [1, 4, 9]);
        assert_eq!(eval!(/= [3, 2, 1], [1, 2, 3]), [3, 1, 0]);
        assert_eq!(eval!(%= [3, 2, 1], [1, 2, 3]), [0, 0, 1]);

        assert_eq!(eval!(&= [0b01, 0b01], [0b00, 0b11]), [0b00, 0b01]);
        assert_eq!(eval!(|= [0b01, 0b01], [0b00, 0b11]), [0b01, 0b11]);
        assert_eq!(eval!(^= [0b01, 0b01], [0b00, 0b11]), [0b01, 0b10]);

        assert_eq!(eval!(<<= [0b0001, 0b0001], [1, 2]), [0b0010, 0b0100]);
        assert_eq!(eval!(>>= [0b0100, 0b0100], [1, 2]), [0b0010, 0b0001]);
    }
}
