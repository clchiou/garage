macro_rules! ensure {
    ($predicate:expr, $span:expr, $message:literal $(,)?) => {
        if !$predicate {
            return Err(::syn::Error::new($span, $message));
        }
    };
}

macro_rules! ensure_none {
    ($value:expr, $span:expr, $message:literal $(,)?) => {
        $crate::error::ensure!($value.is_none(), $span, $message)
    };
}

macro_rules! check_duplicated {
    ($value:expr, $span:expr $(,)?) => {
        $crate::error::ensure_none!($value, $span, "duplicated argument")
    };
}

// As of now, `macro_export` cannot be used in a `proc-macro` crate.
pub(crate) use check_duplicated;
pub(crate) use ensure;
pub(crate) use ensure_none;
