#![feature(box_into_inner)]
#![feature(iter_intersperse)]
#![feature(iterator_try_collect)]

mod actor;
mod arg;
mod arg_parse;
mod attr;
mod error;
mod generic;
mod replace;

#[cfg(test)]
mod testing;

use proc_macro::TokenStream;
use syn::ItemImpl;

use crate::actor::ActorArgs;

//
// Implementer's Notes: The Rust community does not seem to have a term for the opposite of
// "turbofish" (i.e., a path with its generic parameters stripped off).  We take the liberty of
// naming it "simple path".
//

#[proc_macro_attribute]
pub fn actor(args: TokenStream, input: TokenStream) -> TokenStream {
    actor::actor(
        syn::parse_macro_input!(args as ActorArgs),
        syn::parse_macro_input!(input as ItemImpl),
    )
    .unwrap_or_else(|error| {
        let compile_errors = error.to_compile_error();
        quote::quote!(#compile_errors)
    })
    .into()
}
