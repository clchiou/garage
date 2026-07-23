use std::borrow::{Borrow, Cow};
use std::ops::{Residual, Try};

pub trait CowExt<'a, T>
where
    T: ToOwned + ?Sized + 'a,
{
    fn map<F, U>(self, f: F) -> Cow<'a, U>
    where
        F: FnOnce(&T) -> &U,
        U: ToOwned + ?Sized + 'a;

    // We attempted to express this HRTB `for<'b> FnOnce<(&'b T,), Output: Try<Output = &'b U>>`,
    // but this is not valid in Rust.  Despite considerable effort exploring workarounds, none were
    // satisfactory.  `CowTryMapFn` cannot accept variant constructors (e.g., `Some`) or closures
    // without explicit lifetime annotations.
    fn try_map<F, U, R>(self, f: F) -> <R as Residual<Cow<'a, U>>>::TryType
    where
        for<'b> F: CowTryMapFn<'b, T, U, R>,
        U: ToOwned + ?Sized + 'a,
        R: Residual<Cow<'a, U>>;

    // Alternatively, we can forgo HRTBs and use `unsafe`.  This approach supports both variant
    // constructors and closures, but introduces a safety requirement: `R` must never borrow from
    // `Cow<T>`.  Because the compiler cannot ensure this for `Cow<'stsatic, T>`, the function is
    // marked `unsafe`.
    /// # Safety
    ///
    /// Any residual value returned by `f` must not contain references tied to `Cow<T>`.
    unsafe fn try_map_<F, U, R>(self, f: F) -> <R as Residual<Cow<'a, U>>>::TryType
    where
        F: FnOnce<(&'a T,), Output: Try<Output = &'a U, Residual = R>>,
        U: ToOwned + ?Sized + 'a,
        R: Residual<Cow<'a, U>> + 'static;
}

impl<'a, T> CowExt<'a, T> for Cow<'a, T>
where
    T: ToOwned + ?Sized + 'a,
{
    fn map<F, U>(self, f: F) -> Cow<'a, U>
    where
        F: FnOnce(&T) -> &U,
        U: ToOwned + ?Sized + 'a,
    {
        match self {
            Self::Borrowed(x) => Cow::Borrowed(f(x)),
            Self::Owned(x) => Cow::Owned(f(x.borrow()).to_owned()),
        }
    }

    fn try_map<F, U, R>(self, f: F) -> <R as Residual<Cow<'a, U>>>::TryType
    where
        for<'b> F: CowTryMapFn<'b, T, U, R>,
        U: ToOwned + ?Sized + 'a,
        R: Residual<Cow<'a, U>>,
    {
        Try::from_output(match self {
            Self::Borrowed(x) => Cow::Borrowed(f(x)?),
            Self::Owned(x) => Cow::Owned(f(x.borrow())?.to_owned()),
        })
    }

    unsafe fn try_map_<F, U, R>(self, f: F) -> <R as Residual<Cow<'a, U>>>::TryType
    where
        F: FnOnce<(&'a T,), Output: Try<Output = &'a U, Residual = R>>,
        U: ToOwned + ?Sized + 'a,
        R: Residual<Cow<'a, U>> + 'static,
    {
        Try::from_output(match self {
            Self::Borrowed(x) => Cow::Borrowed(f(x)?),
            // This should be safe because `f`'s output is immediately converted into an owned
            // value, and the caller ensures that residual cannot borrow from `x`.
            // TODO: Can we prove this?
            Self::Owned(x) => Cow::Owned(f(unsafe { &*(x.borrow() as *const T) })?.to_owned()),
        })
    }
}

pub trait CowTryMapFn<'a, T, U, R>
where
    Self: FnOnce<(&'a T,), Output: Try<Output = &'a U, Residual = R>>,
    T: ?Sized + 'a,
    U: ?Sized + 'a,
{
    fn call(self, x: &'a T) -> Self::Output;
}

impl<'a, F, T, U, R> CowTryMapFn<'a, T, U, R> for F
where
    F: FnOnce<(&'a T,), Output: Try<Output = &'a U, Residual = R>>,
    T: ?Sized + 'a,
    U: ?Sized + 'a,
{
    fn call(self, x: &'a T) -> Self::Output {
        self(x)
    }
}
