use std::any;
use std::fmt::Debug;

pub trait MustFrom<T>: Sized {
    fn must_from(value: T) -> Self;
}

pub trait MustInto<T>: Sized {
    fn must_into(self) -> T;
}

impl<This, T> MustFrom<T> for This
where
    This: TryFrom<T>,
    <This as TryFrom<T>>::Error: Debug,
{
    fn must_from(value: T) -> Self {
        #[allow(clippy::expect_fun_call)]
        This::try_from(value).expect(any::type_name::<This>())
    }
}

impl<This, T> MustInto<T> for This
where
    T: MustFrom<This>,
{
    fn must_into(self) -> T {
        T::must_from(self)
    }
}
