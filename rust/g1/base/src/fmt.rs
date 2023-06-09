use std::fmt;

pub use g1_base_derive::DebugExt;

/// Escapes non-ASCII characters in a slice to produce `fmt::Debug` output.
pub struct EscapeAscii<'a>(pub &'a [u8]);

impl<'a> fmt::Debug for EscapeAscii<'a> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "\"{}\"", self.0.escape_ascii())
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
        let escaped = b"\t".as_slice();
        assert_eq!(format!("{:?}", EscapeAscii(escaped)), "\"\\t\"");
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
