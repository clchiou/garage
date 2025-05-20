use proc_macro2::TokenStream;
use syn::{DeriveInput, Error, Field, punctuated::Punctuated, token::Comma};

use crate::{
    attr::{self, AttrArgType},
    generate,
};

pub(crate) fn derive(input: DeriveInput) -> Result<TokenStream, Error> {
    let cmps = generate_comparisons(crate::get_fields(&input).ok_or_else(error::unsupported)?)?;
    let name = &input.ident;
    let generic_params = generate::generic_params(&input);
    let generic_param_names = generate::generic_param_names(&input);
    let where_clause = generate::where_clause(&input);
    Ok(quote::quote! {
        impl #generic_params ::std::cmp::PartialEq for #name #generic_param_names #where_clause {
            fn eq(&self, other: &Self) -> bool {
                #(#cmps)&&*
            }
        }
    })
}

fn generate_comparisons(fields: &Punctuated<Field, Comma>) -> Result<Vec<TokenStream>, Error> {
    if fields.is_empty() {
        return Err(error::unsupported());
    }
    let mut comparisons = Vec::new();
    for (i, field) in fields.iter().enumerate() {
        if !should_skip_field(field)? {
            let field = generate::field(i, field);
            comparisons.push(quote::quote!(self.#field == other.#field));
        }
    }
    if comparisons.is_empty() {
        return Err(error::all_skipped());
    }
    Ok(comparisons)
}

fn should_skip_field(field: &Field) -> Result<bool, Error> {
    Ok(attr::parse_field_attr_args(
        field,
        "partial_eq",
        &[("skip", AttrArgType::Flag)],
        &mut [None],
    )?[0]
        .is_some())
}

mod error {
    use syn::Error;

    pub(super) fn unsupported() -> Error {
        crate::new_error("`#[derive(PartialEqExt)]` only supports non-unit, non-empty structs")
    }

    pub(super) fn all_skipped() -> Error {
        crate::new_error("all fields are annotated with `#[partial_eq(skip)]`")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn partial_eq() {
        let input = syn::parse_quote! {
            struct r#Foo {
                x: u8,
            }
        };
        let expect = quote::quote! {
            impl ::std::cmp::PartialEq for r#Foo {
                fn eq(&self, other: &Self) -> bool {
                    self.x == other.x
                }
            }
        };
        crate::assert_ok!(derive(input), expect);

        let input = syn::parse_quote! {
            struct r#Foo(u8, u8);
        };
        let expect = quote::quote! {
            impl ::std::cmp::PartialEq for r#Foo {
                fn eq(&self, other: &Self) -> bool {
                    self.0 == other.0 && self.1 == other.1
                }
            }
        };
        crate::assert_ok!(derive(input), expect);

        let input = syn::parse_quote! {
            struct r#Foo {
                x: u8,
                #[partial_eq(skip)]
                y: u8,
            }
        };
        let expect = quote::quote! {
            impl ::std::cmp::PartialEq for r#Foo {
                fn eq(&self, other: &Self) -> bool {
                    self.x == other.x
                }
            }
        };
        crate::assert_ok!(derive(input), expect);

        let input = syn::parse_quote! {
            struct r#Foo(#[partial_eq(skip)] u8, #[partial_eq(skip)] u8);
        };
        crate::assert_err!(derive(input), error::all_skipped());

        let input = syn::parse_quote! {
            struct Foo;
        };
        crate::assert_err!(derive(input), error::unsupported());
        let input = syn::parse_quote! {
            struct Foo {}
        };
        crate::assert_err!(derive(input), error::unsupported());
        let input = syn::parse_quote! {
            struct Foo ();
        };
        crate::assert_err!(derive(input), error::unsupported());
        let input = syn::parse_quote! {
            enum Foo {
                X,
            }
        };
        crate::assert_err!(derive(input), error::unsupported());
    }
}
