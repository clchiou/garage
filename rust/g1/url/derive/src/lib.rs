//! `ParseQuery` and `UpdateQuery` Derive Macro
//!
//! * This is intended for deriving simple `ParseQuery` and `UpdateQuery`.  For complex use cases,
//!   you should implement them manually.
//!
//! * The basic idea is that the derived `ParseQuery` and `UpdateQuery` are inverses of each other,
//!   or as close as possible.  The derived `ParseQuery` fills in absent query parameters with
//!   default values, while the derived `UpdateQuery` removes struct fields that are equal to their
//!   default values from the URL query string.  You can change the behavior of `UpdateQuery` by
//!   specifying the `insert_default` attribute.
//!
//! * We provide special handling for `Option` fields.  Their default value is fixed to `None`, and
//!   you cannot change it.
//!
//! * We require that every struct field type implements `Display` and `FromStr`, and that each
//!   type's `FromStr` can parse the output of its `Display`.  If `insert_default` is not
//!   specified, we also require `Default` and `PartialEq` (to check whether a field's value equals
//!   its default, and remove it if it does).
//!
//! * We do not provide a `flatten` attribute because it is quite complex and not worth the effort.
//!   To compensate, we provide special handling for `BTreeMap` and `HashMap`, making them behave
//!   as though `flatten` were applied.
//!
//! * Note, however, that `Vec` is not (or may not be) supported, since `g1_url::QueryBuilder`
//!   removes duplicate query keys.
//!

#![feature(iterator_try_collect)]

mod codegen;
mod parse_query;
mod update_query;

use proc_macro::TokenStream;
use syn::DeriveInput;

#[proc_macro_derive(ParseQuery, attributes(g1_url))]
pub fn derive_parse_query(input: TokenStream) -> TokenStream {
    parse_query::derive(syn::parse_macro_input!(input as DeriveInput))
        .unwrap_or_else(|error| {
            let compile_errors = error.to_compile_error();
            quote::quote!(#compile_errors)
        })
        .into()
}

#[proc_macro_derive(UpdateQuery, attributes(g1_url))]
pub fn derive_update_query(input: TokenStream) -> TokenStream {
    update_query::derive(syn::parse_macro_input!(input as DeriveInput))
        .unwrap_or_else(|error| {
            let compile_errors = error.to_compile_error();
            quote::quote!(#compile_errors)
        })
        .into()
}
