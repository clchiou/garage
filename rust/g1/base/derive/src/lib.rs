#![cfg_attr(test, feature(assert_matches))]

mod attr;
mod debug;
mod deref;
mod generate;
mod partial_eq;

use std::fmt;

use proc_macro2::{Span, TokenStream};
use syn::{
    Data, DataStruct, DeriveInput, Error, Field, Fields, punctuated::Punctuated, token::Comma,
};

#[proc_macro_derive(DebugExt, attributes(debug))]
pub fn derive_debug_ext(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    derive_with(input, debug::derive)
}

#[proc_macro_derive(Deref, attributes(deref))]
pub fn derive_deref(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    derive_with(input, deref::derive_deref)
}

#[proc_macro_derive(DerefMut, attributes(deref))]
pub fn derive_deref_mut(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    derive_with(input, deref::derive_deref_mut)
}

#[proc_macro_derive(PartialEqExt, attributes(partial_eq))]
pub fn derive_partial_eq_ext(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    derive_with(input, partial_eq::derive)
}

fn derive_with<F>(input: proc_macro::TokenStream, derive: F) -> proc_macro::TokenStream
where
    F: FnOnce(DeriveInput) -> Result<TokenStream, Error>,
{
    derive(syn::parse_macro_input!(input as DeriveInput))
        .unwrap_or_else(|error| {
            let compile_errors = error.to_compile_error();
            quote::quote!(#compile_errors)
        })
        .into()
}

pub(crate) fn is_tuple_struct(input: &DeriveInput) -> bool {
    matches!(
        input.data,
        Data::Struct(DataStruct {
            fields: Fields::Unnamed(_),
            ..
        })
    )
}

pub(crate) fn get_fields(input: &DeriveInput) -> Option<&Punctuated<Field, Comma>> {
    match &input.data {
        Data::Struct(DataStruct { fields, .. }) => match fields {
            Fields::Named(fields) => Some(&fields.named),
            Fields::Unnamed(fields) => Some(&fields.unnamed),
            Fields::Unit => None,
        },
        Data::Enum(_) | Data::Union(_) => None,
    }
}

pub(crate) fn new_error<T: fmt::Display>(message: T) -> Error {
    Error::new(Span::call_site(), message)
}

#[cfg(test)]
mod test_harness {
    // We provide these macro helpers because `proc_macro2::TokenStream` and `syn::Error` do not
    // implement `PartialEq`.

    #[macro_export]
    macro_rules! assert_ok {
        ($ok:expr, $expect:expr $(,)?) => {
            ::std::assert_eq!($ok.unwrap().to_string(), $expect.to_string());
        };
    }

    #[macro_export]
    macro_rules! assert_err {
        ($err:expr, $expect:expr $(,)?) => {
            ::std::assert_eq!($err.unwrap_err().to_string(), $expect.to_string());
        };
    }
}
