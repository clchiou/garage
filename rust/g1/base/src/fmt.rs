use std::fmt;
use std::sync::Arc;

pub use g1_base_derive::DebugExt;

/// Escapes non-ASCII characters in a slice to produce `fmt::Debug` output.
pub struct EscapeAscii<'a, T: ?Sized = [u8]>(pub &'a T);

// TODO: Make `EscapeAscii` support `&Some(&[T; N])` and `&Some(&&[T])`.
impl<'a, T> fmt::Debug for EscapeAscii<'a, Option<T>>
where
    EscapeAscii<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.0 {
            Some(some) => f.debug_tuple("Some").field(&EscapeAscii(some)).finish(),
            None => write!(f, "None"),
        }
    }
}

impl<'a, T> fmt::Debug for EscapeAscii<'a, Arc<T>>
where
    EscapeAscii<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        EscapeAscii(&**self.0).fmt(f)
    }
}

// TODO: I do not know why, but `impl for EscapeAscii<'a, Arc<T>>` does not seem to cover this
// case.
impl<'a, T> fmt::Debug for EscapeAscii<'a, Arc<[T]>>
where
    EscapeAscii<'a, [T]>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        EscapeAscii(&**self.0).fmt(f)
    }
}

// TODO: Make `EscapeAscii` support `&[&[T; N]]` and `&[&&[T]]`.
impl<'a, T> fmt::Debug for EscapeAscii<'a, Vec<T>>
where
    EscapeAscii<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        EscapeAscii(self.0.as_slice()).fmt(f)
    }
}

impl<'a, T, const N: usize> fmt::Debug for EscapeAscii<'a, [T; N]>
where
    EscapeAscii<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        EscapeAscii(self.0.as_slice()).fmt(f)
    }
}

impl<'a, T> fmt::Debug for EscapeAscii<'a, &[T]>
where
    EscapeAscii<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        EscapeAscii(*self.0).fmt(f)
    }
}

impl<'a, T> fmt::Debug for EscapeAscii<'a, [T]>
where
    EscapeAscii<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_list()
            .entries(self.0.iter().map(EscapeAscii))
            .finish()
    }
}

impl<'a, const N: usize> fmt::Debug for EscapeAscii<'a, [u8; N]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        EscapeAscii(self.0.as_slice()).fmt(f)
    }
}

impl<'a> fmt::Debug for EscapeAscii<'a, &[u8]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        EscapeAscii(*self.0).fmt(f)
    }
}

impl<'a> fmt::Debug for EscapeAscii<'a, [u8]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "\"{}\"", self.0.escape_ascii())
    }
}

/// Formats a bytes slice into a hex string.
pub struct Hex<'a, T: ?Sized = [u8]>(pub &'a T);

// TODO: Make `Hex` support `&Some(&[T; N])` and `&Some(&&[T])`.
impl<'a, T> fmt::Debug for Hex<'a, Option<T>>
where
    Hex<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.0 {
            Some(some) => f.debug_tuple("Some").field(&Hex(some)).finish(),
            None => write!(f, "None"),
        }
    }
}

impl<'a, T> fmt::Debug for Hex<'a, Arc<T>>
where
    Hex<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        Hex(&**self.0).fmt(f)
    }
}

// TODO: I do not know why, but `impl for Hex<'a, Arc<T>>` does not seem to cover this case.
impl<'a, T> fmt::Debug for Hex<'a, Arc<[T]>>
where
    Hex<'a, [T]>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        Hex(&**self.0).fmt(f)
    }
}

// TODO: Make `Hex` support `&[&[T; N]]` and `&[&&[T]]`.
impl<'a, T> fmt::Debug for Hex<'a, Vec<T>>
where
    Hex<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        Hex(self.0.as_slice()).fmt(f)
    }
}

impl<'a, T, const N: usize> fmt::Debug for Hex<'a, [T; N]>
where
    Hex<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        Hex(self.0.as_slice()).fmt(f)
    }
}

impl<'a, T> fmt::Debug for Hex<'a, &[T]>
where
    Hex<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        Hex(*self.0).fmt(f)
    }
}

impl<'a, T> fmt::Debug for Hex<'a, [T]>
where
    Hex<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_list().entries(self.0.iter().map(Hex)).finish()
    }
}

impl<'a, const N: usize> fmt::Debug for Hex<'a, [u8; N]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        Hex(self.0.as_slice()).fmt(f)
    }
}

impl<'a> fmt::Debug for Hex<'a, &[u8]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        Hex(*self.0).fmt(f)
    }
}

impl<'a> fmt::Debug for Hex<'a, [u8]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        for byte in self.0 {
            write!(f, "{:02x}", byte)?;
        }
        Ok(())
    }
}

/// Recursively inserts placeholders for a value of a type that does not "fully" implement
/// `std::fmt::Debug`.
pub struct InsertPlaceholder<'a, T: ?Sized>(pub &'a T);

/// Inserts a placeholder for a value of a type that does not implement `std::fmt::Debug`.
struct InsertPlaceholderBase<T>(pub T);

impl<'a, T> fmt::Debug for InsertPlaceholder<'a, Option<T>> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.0 {
            Some(some) => f
                .debug_tuple("Some")
                .field(&InsertPlaceholder(some))
                .finish(),
            None => write!(f, "None"),
        }
    }
}

impl<'a, T, E> fmt::Debug for InsertPlaceholder<'a, Result<T, E>> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.0 {
            Ok(ok) => f.debug_tuple("Ok").field(&InsertPlaceholder(ok)).finish(),
            Err(err) => f.debug_tuple("Err").field(&InsertPlaceholder(err)).finish(),
        }
    }
}

macro_rules! generate_tuple {
    ($($name:ident),* $(,)?) => {
        generate_tuple!(@loop ; $($name)*);
    };

    (@loop $($name:ident)* ; $head:ident $($tail:ident)*) => {
        generate_tuple!(@gen $($name)*);
        generate_tuple!(@loop $($name)* $head ; $($tail)*);
    };
    (@loop $($name:ident)* ; ) => {
        generate_tuple!(@gen $($name)*);
    };

    (@gen $($name:ident)+) => {
        impl<'a, $($name),+> fmt::Debug for InsertPlaceholder<'a, ($($name,)+)> {
            #[allow(non_snake_case)]
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                let mut builder = f.debug_tuple("");
                let ($($name,)+) = &self.0;
                $(builder.field(&InsertPlaceholder($name));)+
                builder.finish()
            }
        }
    };
    (@gen) => {};
}

generate_tuple!(T0, T1, T2, T3, T4, T5, T6, T7, T8, T9, T10, T11);

impl<'a, T> fmt::Debug for InsertPlaceholder<'a, Vec<T>> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        InsertPlaceholder(self.0.as_slice()).fmt(f)
    }
}

impl<'a, T, const N: usize> fmt::Debug for InsertPlaceholder<'a, [T; N]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        InsertPlaceholder(self.0.as_slice()).fmt(f)
    }
}

impl<'a, T> fmt::Debug for InsertPlaceholder<'a, &'a [T]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        InsertPlaceholder(*self.0).fmt(f)
    }
}

impl<'a, T> fmt::Debug for InsertPlaceholder<'a, [T]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_list()
            .entries(self.0.iter().map(InsertPlaceholder))
            .finish()
    }
}

impl<'a, T> fmt::Debug for InsertPlaceholder<'a, T> {
    default fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        InsertPlaceholderBase(&self.0).fmt(f)
    }
}

#[rustc_unsafe_specialization_marker]
trait HaveImplDebug: fmt::Debug {}

impl<T: fmt::Debug> HaveImplDebug for T {}

impl<T> fmt::Debug for InsertPlaceholderBase<T> {
    default fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "_")
    }
}

impl<T: HaveImplDebug> fmt::Debug for InsertPlaceholderBase<T> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(f)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn escape_ascii() {
        // TODO: Turn this into a generic function.
        macro_rules! test {
            ($data:expr, $expect:expr $(,)?) => {
                assert_eq!(format!("{:?}", EscapeAscii($data)), $expect);
            };
        }

        test!(b"spam \tegg\r\n", "\"spam \\tegg\\r\\n\"");

        let array: [u8; 8] = *b"deadbeef";
        let slice = array.as_slice();

        test!(&Some(slice), "Some(\"deadbeef\")");
        test!(&Some(Some(slice)), "Some(Some(\"deadbeef\"))");
        test!(&None as &Option<&[u8]>, "None");
        test!(&None as &Option<Option<&[u8]>>, "None");

        let arc: Arc<[u8; 8]> = Arc::new(array.clone());
        test!(&arc, "\"deadbeef\"");
        test!(&Some(arc.clone()), "Some(\"deadbeef\")");
        let arc: Arc<[u8]> = Arc::from(slice);
        test!(&arc, "\"deadbeef\"");
        test!(&Some(arc.clone()), "Some(\"deadbeef\")");
        test!(&Arc::new(Some(slice)), "Some(\"deadbeef\")");

        test!(&vec![slice], "[\"deadbeef\"]");
        test!(&vec![Some(slice), None], "[Some(\"deadbeef\"), None]");
        test!(&[slice], "[\"deadbeef\"]");
        test!([slice].as_slice(), "[\"deadbeef\"]");
        test!(&[slice].as_slice(), "[\"deadbeef\"]");

        test!(&array, "\"deadbeef\"");
        test!(slice, "\"deadbeef\"");
        test!(&slice, "\"deadbeef\"");
    }

    #[test]
    fn hex() {
        // TODO: Turn this into a generic function.
        macro_rules! test {
            ($data:expr, $expect:expr $(,)?) => {
                assert_eq!(format!("{:?}", Hex($data)), $expect);
            };
        }

        let array = [0xdeu8, 0xad, 0xbe, 0xef];
        let slice = array.as_slice();

        test!(&Some(slice), "Some(deadbeef)");
        test!(&Some(Some(slice)), "Some(Some(deadbeef))");
        test!(&None as &Option<&[u8]>, "None");
        test!(&None as &Option<Option<&[u8]>>, "None");

        let arc: Arc<[u8; 4]> = Arc::new(array.clone());
        test!(&arc, "deadbeef");
        test!(&Some(arc.clone()), "Some(deadbeef)");
        let arc: Arc<[u8]> = Arc::from(slice);
        test!(&arc, "deadbeef");
        test!(&Some(arc.clone()), "Some(deadbeef)");
        test!(&Arc::new(Some(slice)), "Some(deadbeef)");

        test!(&vec![slice], "[deadbeef]");
        test!(&vec![Some(slice), None], "[Some(deadbeef), None]");
        test!(&[slice], "[deadbeef]");
        test!([slice].as_slice(), "[deadbeef]");
        test!(&[slice].as_slice(), "[deadbeef]");

        test!(&array, "deadbeef");
        test!(slice, "deadbeef");
        test!(&slice, "deadbeef");
    }

    #[derive(Debug)]
    struct YesDebug;

    struct NoDebug;

    #[test]
    fn insert_placeholder() {
        fn test<T>(value: T, expect: &str) {
            assert_eq!(format!("{:?}", InsertPlaceholder(&value)), expect);
        }

        test(42, "42");
        test(YesDebug, "YesDebug");
        test(NoDebug, "_");
        test(insert_placeholder, "_");

        test(Some(YesDebug), "Some(YesDebug)");
        test(Some(Some(YesDebug)), "Some(Some(YesDebug))");
        test::<Option<YesDebug>>(None, "None");
        test::<Option<Option<YesDebug>>>(None, "None");

        test(Some(NoDebug), "Some(_)");
        test(Some(Some(NoDebug)), "Some(Some(_))");
        test::<Option<NoDebug>>(None, "None");
        test::<Option<Option<NoDebug>>>(None, "None");

        test::<Result<YesDebug, NoDebug>>(Ok(YesDebug), "Ok(YesDebug)");
        test::<Result<Result<YesDebug, NoDebug>, NoDebug>>(Ok(Ok(YesDebug)), "Ok(Ok(YesDebug))");
        test::<Result<YesDebug, NoDebug>>(Err(NoDebug), "Err(_)");
        test::<Result<YesDebug, Result<YesDebug, NoDebug>>>(Err(Err(NoDebug)), "Err(Err(_))");

        test((), "()");
        test((YesDebug, NoDebug), "(YesDebug, _)");
        test((YesDebug, (YesDebug, NoDebug)), "(YesDebug, (YesDebug, _))");
        test(
            (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),
            "(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)",
        );

        test(vec![YesDebug], "[YesDebug]");
        test(vec![Ok(YesDebug), Err(NoDebug)], "[Ok(YesDebug), Err(_)]");

        test([YesDebug], "[YesDebug]");
        test([Ok(YesDebug), Err(NoDebug)], "[Ok(YesDebug), Err(_)]");

        test([YesDebug].as_slice(), "[YesDebug]");
        test(
            [Ok(YesDebug), Err(NoDebug)].as_slice(),
            "[Ok(YesDebug), Err(_)]",
        );
    }

    #[test]
    fn insert_placeholder_base() {
        fn test<T>(value: T, expect: &str) {
            assert_eq!(format!("{:?}", InsertPlaceholderBase(&value)), expect);
            assert_eq!(format!("{:?}", InsertPlaceholderBase(value)), expect);
        }

        test(42, "42");
        test(YesDebug, "YesDebug");
        test(NoDebug, "_");
        test(insert_placeholder_base, "_");

        test(Some(YesDebug), "Some(YesDebug)");
        test::<Option<YesDebug>>(None, "None");

        test(Some(NoDebug), "_");
        test::<Option<NoDebug>>(None, "_");

        test::<Result<YesDebug, NoDebug>>(Ok(YesDebug), "_");
        test::<Result<YesDebug, NoDebug>>(Err(NoDebug), "_");

        test((), "()");
        test((YesDebug, NoDebug), "_");
        test((YesDebug, (YesDebug, NoDebug)), "_");
        test(
            (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),
            "(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)",
        );

        test(vec![YesDebug], "[YesDebug]");
        test(vec![Ok(YesDebug), Err(NoDebug)], "_");

        test([YesDebug], "[YesDebug]");
        test([Ok(YesDebug), Err(NoDebug)], "_");

        test([YesDebug].as_slice(), "[YesDebug]");
        test([Ok(YesDebug), Err(NoDebug)].as_slice(), "_");
    }
}
