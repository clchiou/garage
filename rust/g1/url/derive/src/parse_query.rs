use proc_macro2::TokenStream;
use syn::{DeriveInput, Error};

use crate::codegen::{Codegen, ContainerType};

pub(crate) fn derive(input: DeriveInput) -> Result<TokenStream, Error> {
    Ok(Codegen::parse(&input)?.gen_impl_parse_query())
}

impl Codegen<'_> {
    fn gen_impl_parse_query(&self) -> TokenStream {
        let type_name = self.ident;
        let (impl_generics, type_generics, _) = self.generics.split_for_impl();

        let where_clause = self.where_clause(
            true, // require_default
            |param| syn::parse_quote! { #param: ::std::str::FromStr<Err: ::std::error::Error> },
        );

        let match_loop = self.gen_match_loop();

        // This is not bulletproof, but we use longer lifetime names to prevent conflicts with the
        // caller's names.
        quote::quote! {
            impl #impl_generics ::g1_url::ParseQuery for #type_name #type_generics #where_clause {
                type Error = ::std::boxed::Box<dyn ::std::error::Error>;

                fn parse_query<'parse_query, I>(
                    __query_pairs: I,
                ) -> ::std::result::Result<Self, Self::Error>
                where
                    I: ::std::iter::Iterator<
                            Item = (
                                ::std::borrow::Cow<'parse_query, str>,
                                ::std::borrow::Cow<'parse_query, str>,
                            ),
                        >,
                {
                    let mut __self = Self::default();
                    #match_loop
                    ::std::result::Result::Ok(__self)
                }
            }
        }
    }

    fn gen_match_loop(&self) -> Option<TokenStream> {
        if self.fields.is_empty() {
            return None;
        }

        let match_arms = self.fields.iter().filter_map(|field| {
            let name = &field.ident;
            let parse_value = match field.parse_with() {
                Some(parse_with) => quote::quote! { #parse_with(__value) },
                None => quote::quote! { __value.parse() },
            };
            let parse = match field.container_type {
                ContainerType::Map => return None,
                ContainerType::Option => quote::quote! {
                    __self.#name = Some(#parse_value?)
                },
                ContainerType::None => quote::quote! {
                    __self.#name = #parse_value?
                },
            };
            let key = field.key();
            Some(quote::quote! { #key => #parse, })
        });

        let match_else_arm = self
            .fields
            .iter()
            .find_map(|field| {
                (field.container_type == ContainerType::Map).then(|| {
                    let name = &field.ident;
                    let parse_value = match field.parse_with() {
                        Some(parse_with) => quote::quote! { #parse_with(__value) },
                        None => quote::quote! { __value.parse() },
                    };
                    quote::quote! {
                        _ => {
                            __self.#name.insert(__key.into(), #parse_value?);
                        }
                    }
                })
            })
            .unwrap_or_else(|| quote::quote! { _ => {} });

        Some(quote::quote! {
            for (__key, __value) in __query_pairs {
                match __key.as_ref() {
                    #(#match_arms)*
                    #match_else_arm
                }
            }
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_derive() {
        fn test_ok(input: DeriveInput, expect: TokenStream) {
            assert_eq!(derive(input).unwrap().to_string(), expect.to_string());
        }

        test_ok(
            syn::parse_quote! {
                struct Foo<'a, K: Debug, V, const N: usize> where V: Debug {
                    map: HashMap<K, V>,
                    option: Option<T>,
                    r#try: String,

                    #[g1_url(rename = "spam egg", insert_default)]
                    r#loop: u64,

                    #[g1_url(skip)]
                    skipped: u64,
                }
            },
            quote::quote! {
                impl<'a, K: Debug, V, const N: usize> ::g1_url::ParseQuery for Foo<'a, K, V, N>
                where
                    V: Debug,
                    Self: ::std::default::Default,
                    K: ::std::str::FromStr<Err: ::std::error::Error>,
                    V: ::std::str::FromStr<Err: ::std::error::Error>
                {
                    type Error = ::std::boxed::Box<dyn ::std::error::Error>;

                    fn parse_query<'parse_query, I>(
                        __query_pairs: I,
                    ) -> ::std::result::Result<Self, Self::Error>
                    where
                        I: ::std::iter::Iterator<
                                Item = (
                                    ::std::borrow::Cow<'parse_query, str>,
                                    ::std::borrow::Cow<'parse_query, str>,
                                ),
                            >,
                    {
                        let mut __self = Self::default();
                        for (__key, __value) in __query_pairs {
                            match __key.as_ref() {
                                "option" => __self.option = Some(__value.parse()?),
                                "try" => __self.r#try = __value.parse()?,
                                "spam egg" => __self.r#loop = __value.parse()?,
                                _ => {
                                    __self.map.insert(__key.into(), __value.parse()?);
                                }
                            }
                        }
                        ::std::result::Result::Ok(__self)
                    }
                }
            },
        );

        test_ok(
            syn::parse_quote! {
                #[g1_url(insert_default)]
                struct Foo {
                    #[g1_url(insert_default)]
                    x: String,
                }
            },
            quote::quote! {
                impl ::g1_url::ParseQuery for Foo
                where
                    Self: ::std::default::Default
                {
                    type Error = ::std::boxed::Box<dyn ::std::error::Error>;

                    fn parse_query<'parse_query, I>(
                        __query_pairs: I,
                    ) -> ::std::result::Result<Self, Self::Error>
                    where
                        I: ::std::iter::Iterator<
                                Item = (
                                    ::std::borrow::Cow<'parse_query, str>,
                                    ::std::borrow::Cow<'parse_query, str>,
                                ),
                            >,
                    {
                        let mut __self = Self::default();
                        for (__key, __value) in __query_pairs {
                            match __key.as_ref() {
                                "x" => __self.x = __value.parse()?,
                                _ => {}
                            }
                        }
                        ::std::result::Result::Ok(__self)
                    }
                }
            },
        );

        test_ok(
            syn::parse_quote! {
                struct Foo {
                    #[g1_url(with = "f::<T>")]
                    map: HashMap<K, V>,
                    #[g1_url(parse_with = "g::<T>", to_string_with = "foo")]
                    option: Option<T>,
                    #[g1_url(parse_with = "h::<T>", to_string_with = "foo")]
                    string: String,
                }
            },
            quote::quote! {
                impl ::g1_url::ParseQuery for Foo
                where
                    Self: ::std::default::Default
                {
                    type Error = ::std::boxed::Box<dyn ::std::error::Error>;

                    fn parse_query<'parse_query, I>(
                        __query_pairs: I,
                    ) -> ::std::result::Result<Self, Self::Error>
                    where
                        I: ::std::iter::Iterator<
                                Item = (
                                    ::std::borrow::Cow<'parse_query, str>,
                                    ::std::borrow::Cow<'parse_query, str>,
                                ),
                            >,
                    {
                        let mut __self = Self::default();
                        for (__key, __value) in __query_pairs {
                            match __key.as_ref() {
                                "option" => __self.option = Some(g::<T>(__value)?),
                                "string" => __self.string = h::<T>(__value)?,
                                _ => {
                                    __self.map.insert(__key.into(), f::<T>::parse(__value)?);
                                }
                            }
                        }
                        ::std::result::Result::Ok(__self)
                    }
                }
            },
        );

        test_ok(
            syn::parse_quote! {
                struct Foo {}
            },
            quote::quote! {
                impl ::g1_url::ParseQuery for Foo
                where
                    Self: ::std::default::Default
                {
                    type Error = ::std::boxed::Box<dyn ::std::error::Error>;

                    fn parse_query<'parse_query, I>(
                        __query_pairs: I,
                    ) -> ::std::result::Result<Self, Self::Error>
                    where
                        I: ::std::iter::Iterator<
                                Item = (
                                    ::std::borrow::Cow<'parse_query, str>,
                                    ::std::borrow::Cow<'parse_query, str>,
                                ),
                            >,
                    {
                        let mut __self = Self::default();
                        ::std::result::Result::Ok(__self)
                    }
                }
            },
        );
    }
}
