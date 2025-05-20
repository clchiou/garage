use proc_macro2::TokenStream;
use syn::{ext::IdentExt, DeriveInput, Error, Field};

use crate::{
    attr::{self, AttrArgType, AttrArgValue},
    generate,
};

pub(crate) fn derive(input: DeriveInput) -> Result<TokenStream, Error> {
    let body = generate_body(&input)?;
    let name = &input.ident;
    let generic_params = generate::generic_params(&input);
    let generic_param_names = generate::generic_param_names(&input);
    let where_clause = generate::where_clause(&input);
    Ok(quote::quote! {
        impl #generic_params ::std::fmt::Debug for #name #generic_param_names #where_clause {
            fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
                #body
            }
        }
    })
}

fn generate_body(input: &DeriveInput) -> Result<TokenStream, Error> {
    let fields = crate::get_fields(input).ok_or_else(error::unsupported)?;
    if fields.is_empty() {
        return Err(error::unsupported());
    }

    let is_tuple_struct = crate::is_tuple_struct(input);
    let mut field_name_strings = Vec::with_capacity(fields.len());
    let mut field_exprs = Vec::with_capacity(fields.len());
    for (i, field) in fields.iter().enumerate() {
        let (skip, with) = parse_attr(field)?;
        if !skip {
            let access = generate::field(i, field);
            if !is_tuple_struct {
                field_name_strings.push(field.ident.as_ref().unwrap().to_string());
            }
            field_exprs.push(match with {
                Some(with) => {
                    let with = with.into_assignee_path();
                    quote::quote!(#with(&self.#access))
                }
                None => quote::quote!(self.#access),
            });
        }
    }
    if field_exprs.is_empty() {
        return Err(error::all_skipped());
    }

    let name_string = input.ident.unraw().to_string();
    Ok(if is_tuple_struct {
        quote::quote! {
            f.debug_tuple(#name_string)
                #(.field(&#field_exprs))*
                .finish()
        }
    } else {
        quote::quote! {
            f.debug_struct(#name_string)
                #(.field(#field_name_strings, &#field_exprs))*
                .finish()
        }
    })
}

fn parse_attr(field: &Field) -> Result<(bool, Option<AttrArgValue>), Error> {
    let mut argv = [None, None];
    attr::parse_field_attr_args(
        field,
        "debug",
        &[
            ("skip", AttrArgType::Flag),
            ("with", AttrArgType::AssignPath),
        ],
        &mut argv,
    )?;
    let [skip, with] = argv;
    Ok((skip.is_some(), with))
}

mod error {
    use syn::Error;

    pub(super) fn unsupported() -> Error {
        crate::new_error("`#[derive(DebugExt)]` only supports non-unit, non-empty structs")
    }

    pub(super) fn all_skipped() -> Error {
        crate::new_error("all fields are annotated with `#[debug(skip)]`")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn debug() {
        let input = syn::parse_quote! {
            struct r#Foo {
                x: u8,
            }
        };
        let expect = quote::quote! {
            impl ::std::fmt::Debug for r#Foo {
                fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
                    f.debug_struct("Foo")
                        .field("x", &self.x)
                        .finish()
                }
            }
        };
        crate::assert_ok!(derive(input), expect);

        let input = syn::parse_quote! {
            struct r#Foo(u8);
        };
        let expect = quote::quote! {
            impl ::std::fmt::Debug for r#Foo {
                fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
                    f.debug_tuple("Foo")
                        .field(&self.0)
                        .finish()
                }
            }
        };
        crate::assert_ok!(derive(input), expect);

        let input = syn::parse_quote! {
            struct r#Foo {
                #[debug(skip)]
                x: u8,
                #[debug(with = foo)]
                y: u8,
            }
        };
        let expect = quote::quote! {
            impl ::std::fmt::Debug for r#Foo {
                fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
                    f.debug_struct("Foo")
                        .field("y", &foo(&self.y))
                        .finish()
                }
            }
        };
        crate::assert_ok!(derive(input), expect);

        let input = syn::parse_quote! {
            struct r#Foo(#[debug(with = spam::egg)] u8, #[debug(skip)] u8, u8);
        };
        let expect = quote::quote! {
            impl ::std::fmt::Debug for r#Foo {
                fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
                    f.debug_tuple("Foo")
                        .field(&spam::egg(&self.0))
                        .field(&self.2)
                        .finish()
                }
            }
        };
        crate::assert_ok!(derive(input), expect);

        let input = syn::parse_quote! {
            struct r#Foo(#[debug(skip)] u8, #[debug(skip)] u8);
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
