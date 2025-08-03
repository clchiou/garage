use std::fmt;

use proc_macro2::{Span, TokenStream};
use syn::punctuated::{Pair, Punctuated};
use syn::{Error, Ident};

pub(crate) fn assert_ok<T>(result: Result<T, Error>, expect: T)
where
    T: fmt::Debug + PartialEq,
{
    assert_eq!(result.unwrap(), expect);
}

pub(crate) fn assert_err<T>(result: Result<T, Error>, error: &str)
where
    T: fmt::Debug,
{
    assert_eq!(result.unwrap_err().to_string(), error);
}

pub(crate) fn assert_ts_eq(actual: TokenStream, expect: TokenStream) {
    assert_eq!(actual.to_string(), expect.to_string());
}

pub(crate) fn i(ident: &str) -> Ident {
    Ident::new(ident, Span::call_site())
}

pub(crate) fn ir(ident: &str) -> Ident {
    Ident::new_raw(ident, Span::call_site())
}

pub(crate) fn ps<T, P, const N: usize>(values: [T; N]) -> Punctuated<T, P>
where
    P: Default,
{
    values
        .into_iter()
        .map(|value| Pair::Punctuated(value, Default::default()))
        .collect()
}

macro_rules! replace {
    ($source:ident => $($(.$field:ident)+ = $value:expr),* $(,)?) => {{
        let mut copy = $source.clone();
        $(copy$(.$field)+ = $value;)*
        copy
    }};
}

// As of now, `macro_export` cannot be used in a `proc-macro` crate.
pub(crate) use replace;
