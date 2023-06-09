use proc_macro2::TokenStream;
use syn::{punctuated::Punctuated, token::Comma, DeriveInput, Error, Field};

use crate::{
    attr::{self, AttrArgType},
    gen,
};

pub(crate) fn derive_deref(input: DeriveInput) -> Result<TokenStream, Error> {
    derive(input, generate_deref)
}

pub(crate) fn derive_deref_mut(input: DeriveInput) -> Result<TokenStream, Error> {
    derive(input, generate_deref_mut)
}

fn derive(
    input: DeriveInput,
    generate: fn(&DeriveInput, usize, &Field) -> TokenStream,
) -> Result<TokenStream, Error> {
    let (index, field) = get_target(crate::get_fields(&input).ok_or_else(error::unsupported)?)?;
    Ok(generate(&input, index, field))
}

fn generate_deref(input: &DeriveInput, index: usize, field: &Field) -> TokenStream {
    let name = &input.ident;
    let generic_params = gen::generic_params(input);
    let generic_param_names = gen::generic_param_names(input);
    let where_clause = gen::where_clause(input);
    let target = gen::field(index, field);
    let target_type = &field.ty;
    quote::quote! {
        impl #generic_params ::std::ops::Deref for #name #generic_param_names #where_clause {
            type Target = #target_type;

            fn deref(&self) -> &Self::Target {
                &self.#target
            }
        }
    }
}

fn generate_deref_mut(input: &DeriveInput, index: usize, field: &Field) -> TokenStream {
    let name = &input.ident;
    let generic_params = gen::generic_params(input);
    let generic_param_names = gen::generic_param_names(input);
    let where_clause = gen::where_clause(input);
    let target = gen::field(index, field);
    quote::quote! {
        impl #generic_params ::std::ops::DerefMut for #name #generic_param_names #where_clause {
            fn deref_mut(&mut self) -> &mut Self::Target {
                &mut self.#target
            }
        }
    }
}

fn get_target(fields: &Punctuated<Field, Comma>) -> Result<(usize, &Field), Error> {
    if fields.is_empty() {
        return Err(error::unsupported());
    }
    let mut candidate = None;
    for (i, field) in fields.iter().enumerate() {
        if attr::parse_field_attr_args(
            field,
            "deref",
            &[("target", AttrArgType::Flag)],
            &mut [None],
        )?[0]
            .is_some()
        {
            if candidate.is_some() {
                return Err(error::not_exactly_one_target());
            }
            candidate = Some((i, field));
        }
    }
    if let Some((i, field)) = candidate {
        return Ok((i, field));
    }
    if fields.len() == 1 {
        return Ok((0, &fields[0]));
    }
    Err(error::not_exactly_one_target())
}

mod error {
    use syn::Error;

    pub(super) fn unsupported() -> Error {
        crate::new_error(
            "`#[derive(Deref)]` and `#[derive(DerefMut)]` only supports non-unit, non-empty structs",
        )
    }

    pub(super) fn not_exactly_one_target() -> Error {
        crate::new_error("exactly one field should be annotated with `#[deref(target)]`")
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use syn::FieldsNamed;

    use super::*;

    #[test]
    fn test_get_target() {
        let fields: FieldsNamed = syn::parse_quote!({
            x: u8,
        });
        let fields = fields.named;
        assert_matches!(get_target(&fields), Ok((0, _)));

        let fields: FieldsNamed = syn::parse_quote!({
            #[deref(target)]
            x: u8,
        });
        let fields = fields.named;
        assert_matches!(get_target(&fields), Ok((0, _)));

        let fields: FieldsNamed = syn::parse_quote!({
            x: u8,
            #[deref(target)]
            y: u8,
        });
        let fields = fields.named;
        assert_matches!(get_target(&fields), Ok((1, _)));

        let fields: FieldsNamed = syn::parse_quote!({
            x: u8,
            y: u8,
        });
        let fields = fields.named;
        crate::assert_err!(get_target(&fields), error::not_exactly_one_target());

        let fields: FieldsNamed = syn::parse_quote!({
            #[deref(target)]
            x: u8,
            #[deref(target)]
            y: u8,
        });
        let fields = fields.named;
        crate::assert_err!(get_target(&fields), error::not_exactly_one_target());
    }

    #[test]
    fn deref() {
        let input = syn::parse_quote! {
            struct r#Foo {
                x: u8,
            }
        };
        let expect = quote::quote! {
            impl ::std::ops::Deref for r#Foo {
                type Target = u8;

                fn deref(&self) -> &Self::Target {
                    &self.x
                }
            }
        };
        crate::assert_ok!(derive_deref(input), expect);

        let input = syn::parse_quote! {
            struct r#Foo(u8, #[deref(target)] Vec<u16>);
        };
        let expect = quote::quote! {
            impl ::std::ops::Deref for r#Foo {
                type Target = Vec<u16>;

                fn deref(&self) -> &Self::Target {
                    &self.1
                }
            }
        };
        crate::assert_ok!(derive_deref(input), expect);

        let input = syn::parse_quote! {
            struct FooBar<'a, T>
            where
                T: AsRef<[u8]>,
            {
                x: u8,
                #[deref(target)]
                y: &'a T,
            }
        };
        let expect = quote::quote! {
            impl<'a, T> ::std::ops::Deref for FooBar<'a, T>
            where
                T: AsRef<[u8]>,
            {
                type Target = &'a T;

                fn deref(&self) -> &Self::Target {
                    &self.y
                }
            }
        };
        crate::assert_ok!(derive_deref(input), expect);

        let input = syn::parse_quote! {
            struct r#Foo;
        };
        crate::assert_err!(derive_deref(input), error::unsupported());

        let input = syn::parse_quote! {
            enum Foo {
                X,
            }
        };
        crate::assert_err!(derive_deref(input), error::unsupported());
    }

    #[test]
    fn deref_mut() {
        let input = syn::parse_quote! {
            struct r#Foo {
                x: u8,
            }
        };
        let expect = quote::quote! {
            impl ::std::ops::DerefMut for r#Foo {
                fn deref_mut(&mut self) -> &mut Self::Target {
                    &mut self.x
                }
            }
        };
        crate::assert_ok!(derive_deref_mut(input), expect);

        let input = syn::parse_quote! {
            struct r#Foo(u8, #[deref(target)] Vec<u16>);
        };
        let expect = quote::quote! {
            impl ::std::ops::DerefMut for r#Foo {
                fn deref_mut(&mut self) -> &mut Self::Target {
                    &mut self.1
                }
            }
        };
        crate::assert_ok!(derive_deref_mut(input), expect);

        let input = syn::parse_quote! {
            struct FooBar<'a, T>
            where
                T: AsRef<[u8]>,
            {
                x: u8,
                #[deref(target)]
                y: &'a T,
            }
        };
        let expect = quote::quote! {
            impl<'a, T> ::std::ops::DerefMut for FooBar<'a, T>
            where
                T: AsRef<[u8]>,
            {
                fn deref_mut(&mut self) -> &mut Self::Target {
                    &mut self.y
                }
            }
        };
        crate::assert_ok!(derive_deref_mut(input), expect);

        let input = syn::parse_quote! {
            struct r#Foo;
        };
        crate::assert_err!(derive_deref_mut(input), error::unsupported());

        let input = syn::parse_quote! {
            enum Foo {
                X,
            }
        };
        crate::assert_err!(derive_deref_mut(input), error::unsupported());
    }
}
