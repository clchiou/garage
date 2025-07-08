#![feature(debug_closure_helpers)]

mod optional;

use proc_macro::TokenStream;
use syn::DeriveInput;

///
/// Annotates all `Option<T>` fields with Serde attributes to ensure correct "optional" semantics.
///
/// Almost all fields of BEP-specified types (e.g., `metainfo`) are optional.  However, by default,
/// Serde does not treat `Option<T>` any differently from other types, and additional attributes
/// must be added to an `Option<T>` field to instruct Serde to map the presence or absence of a
/// field to `Some(T)` or `None`.
///
/// It adds the following attributes:
///
/// * `skip_serializing_if = "Option:is_none"`: Instructs Serde to skip serializing fields whose
///   value is `None`.
///
/// * `with = "..."`: Required only for `bt_bencode`, as it maps `Some(T)` to `[T]`, unlike
///   `serde_json`, which maps `Some(T)` to `T` by default.
///
/// * `default`: Enables Serde to treat missing fields as `None` during deserialization.  This is
///   necessary because using `with = "..."` disables Serde's built-in support for optional
///   fields [1], so an explicit `default` annotation is required.
///
/// [1]: https://github.com/serde-rs/serde/blob/master/serde/src/private/de.rs#L23
///
#[proc_macro_attribute]
pub fn optional(_: TokenStream, input: TokenStream) -> TokenStream {
    optional::optional(syn::parse_macro_input!(input as DeriveInput))
        .unwrap_or_else(|error| {
            let compile_errors = error.to_compile_error();
            quote::quote!(#compile_errors)
        })
        .into()
}
