use proc_macro2::TokenStream;
use syn::{DeriveInput, Error};

use crate::codegen::{Codegen, ContainerType};

pub(crate) fn derive(input: DeriveInput) -> Result<TokenStream, Error> {
    Ok(Codegen::parse(&input)?.gen_impl_update_query())
}

impl Codegen<'_> {
    fn gen_impl_update_query(&self) -> TokenStream {
        let type_name = self.ident;
        let (impl_generics, type_generics, _) = self.generics.split_for_impl();

        let require_default = self.fields.iter().any(|field| {
            field.container_type == ContainerType::None
                && !field.insert_default
                && !self.insert_default
        });

        let where_clause = self.where_clause(
            require_default,
            if require_default {
                |param| syn::parse_quote! { #param: ::std::fmt::Display + ::std::cmp::PartialEq }
            } else {
                |param| syn::parse_quote! { #param: ::std::fmt::Display }
            },
        );

        let update_query_body = self.gen_update_query_body(require_default);

        // This is not bulletproof, but we use longer lifetime names to prevent conflicts with the
        // caller's names.
        quote::quote! {
            impl #impl_generics ::g1_url::UpdateQuery for #type_name #type_generics #where_clause {
                fn update_query<'update_query: 'query_builder, 'query_builder>(
                    &'update_query self,
                    __builder: &mut ::g1_url::QueryBuilder<'query_builder>,
                ) {
                    #update_query_body
                }
            }
        }
    }

    fn gen_update_query_body(&self, require_default: bool) -> Option<TokenStream> {
        if self.fields.is_empty() {
            return None;
        }

        // TODO: Consider switching to `const Default` once we upgrade Rust.
        let make_default = require_default.then(|| {
            quote::quote! {
                let __default = Self::default();
            }
        });

        let insert_func = quote::format_ident!("insert");
        let insert_raw_func = quote::format_ident!("insert_raw");
        let remove_func = quote::format_ident!("remove");
        let remove_raw_func = quote::format_ident!("remove_raw");

        let inserts = self.fields.iter().map(|field| {
            let name = &field.ident;
            let key = field.key();

            let (insert, remove) = if field.insert_raw {
                (&insert_raw_func, &remove_raw_func)
            } else {
                (&insert_func, &remove_func)
            };

            match field.container_type {
                ContainerType::Map => {
                    let value_to_string = match field.to_string_with() {
                        Some(to_string_with) => quote::quote! { #to_string_with(__value) },
                        None => quote::quote! { __value.to_string() },
                    };
                    quote::quote! {
                        for (__key, __value) in &self.#name {
                            __builder.#insert(__key.clone(), #value_to_string);
                        }
                    }
                }
                ContainerType::Option => {
                    let value_to_string = match field.to_string_with() {
                        Some(to_string_with) => quote::quote! { #to_string_with(__value) },
                        None => quote::quote! { __value.to_string() },
                    };
                    quote::quote! {
                        match &self.#name {
                            ::std::option::Option::Some(__value) => {
                                __builder.#insert(#key, #value_to_string);
                            }
                            ::std::option::Option::None => {
                                __builder.#remove(#key);
                            }
                        }
                    }
                }
                ContainerType::None => {
                    let name_to_string = match field.to_string_with() {
                        Some(to_string_with) => quote::quote! { #to_string_with(&self.#name) },
                        None => quote::quote! { self.#name.to_string() },
                    };
                    if field.insert_default || self.insert_default {
                        quote::quote! {
                            __builder.#insert(#key, #name_to_string);
                        }
                    } else {
                        quote::quote! {
                            if self.#name == __default.#name {
                                __builder.#remove(#key);
                            } else {
                                __builder.#insert(#key, #name_to_string);
                            }
                        }
                    }
                }
            }
        });

        Some(quote::quote! {
            #make_default
            #(#inserts)*
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
                struct Foo<'c, K, V, T: Debug, const N: usize> where K: Debug {
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
                impl<'c, K, V, T: Debug, const N: usize> ::g1_url::UpdateQuery for Foo<'c, K, V, T, N>
                where
                    K: Debug,
                    Self: ::std::default::Default,
                    K: ::std::fmt::Display + ::std::cmp::PartialEq,
                    V: ::std::fmt::Display + ::std::cmp::PartialEq,
                    T: ::std::fmt::Display + ::std::cmp::PartialEq
                {
                    fn update_query<'update_query: 'query_builder, 'query_builder>(
                        &'update_query self,
                        __builder: &mut ::g1_url::QueryBuilder<'query_builder>,
                    ) {
                        let __default = Self::default();

                        for (__key, __value) in &self.map {
                            __builder.insert(__key.clone(), __value.to_string());
                        }

                        match &self.option {
                            ::std::option::Option::Some(__value) => {
                                __builder.insert("option", __value.to_string());
                            }
                            ::std::option::Option::None => {
                                __builder.remove("option");
                            }
                        }

                        if self.r#try == __default.r#try {
                            __builder.remove("try");
                        } else {
                            __builder.insert("try", self.r#try.to_string());
                        }

                        __builder.insert("spam egg", self.r#loop.to_string());
                    }
                }
            },
        );

        test_ok(
            syn::parse_quote! {
                #[g1_url(insert_default)]
                struct Foo {
                    map: HashMap<(), ()>,
                    option: Option<()>,
                    r#try: String,
                }
            },
            quote::quote! {
                impl ::g1_url::UpdateQuery for Foo {
                    fn update_query<'update_query: 'query_builder, 'query_builder>(
                        &'update_query self,
                        __builder: &mut ::g1_url::QueryBuilder<'query_builder>,
                    ) {
                        for (__key, __value) in &self.map {
                            __builder.insert(__key.clone(), __value.to_string());
                        }

                        match &self.option {
                            ::std::option::Option::Some(__value) => {
                                __builder.insert("option", __value.to_string());
                            }
                            ::std::option::Option::None => {
                                __builder.remove("option");
                            }
                        }

                        __builder.insert("try", self.r#try.to_string());
                    }
                }
            },
        );

        test_ok(
            syn::parse_quote! {
                struct Foo<T> {
                    #[g1_url(insert_default)]
                    x: T,
                    y: Option<T>,
                }
            },
            quote::quote! {
                impl<T> ::g1_url::UpdateQuery for Foo<T>
                where
                    T: ::std::fmt::Display
                {
                    fn update_query<'update_query: 'query_builder, 'query_builder>(
                        &'update_query self,
                        __builder: &mut ::g1_url::QueryBuilder<'query_builder>,
                    ) {
                        __builder.insert("x", self.x.to_string());

                        match &self.y {
                            ::std::option::Option::Some(__value) => {
                                __builder.insert("y", __value.to_string());
                            }
                            ::std::option::Option::None => {
                                __builder.remove("y");
                            }
                        }
                    }
                }
            },
        );

        test_ok(
            syn::parse_quote! {
                struct Foo {
                    #[g1_url(insert_raw)]
                    map: HashMap<K, V>,
                    #[g1_url(insert_raw)]
                    option: Option<T>,
                    #[g1_url(insert_raw)]
                    string: String,
                }
            },
            quote::quote! {
                impl ::g1_url::UpdateQuery for Foo
                where
                    Self: ::std::default::Default
                {
                    fn update_query<'update_query: 'query_builder, 'query_builder>(
                        &'update_query self,
                        __builder: &mut ::g1_url::QueryBuilder<'query_builder>,
                    ) {
                        let __default = Self::default();

                        for (__key, __value) in &self.map {
                            __builder.insert_raw(__key.clone(), __value.to_string());
                        }

                        match &self.option {
                            ::std::option::Option::Some(__value) => {
                                __builder.insert_raw("option", __value.to_string());
                            }
                            ::std::option::Option::None => {
                                __builder.remove_raw("option");
                            }
                        }

                        if self.string == __default.string {
                            __builder.remove_raw("string");
                        } else {
                            __builder.insert_raw("string", self.string.to_string());
                        }
                    }
                }
            },
        );

        test_ok(
            syn::parse_quote! {
                struct Foo {
                    #[g1_url(with = "f::<T>")]
                    map: HashMap<K, V>,
                    #[g1_url(parse_with = "foo", to_string_with = "g::<T>")]
                    option: Option<T>,
                    #[g1_url(parse_with = "foo", to_string_with = "h::<T>")]
                    string: String,
                }
            },
            quote::quote! {
                impl ::g1_url::UpdateQuery for Foo
                where
                    Self: ::std::default::Default
                {
                    fn update_query<'update_query: 'query_builder, 'query_builder>(
                        &'update_query self,
                        __builder: &mut ::g1_url::QueryBuilder<'query_builder>,
                    ) {
                        let __default = Self::default();

                        for (__key, __value) in &self.map {
                            __builder.insert(__key.clone(), f::<T>::to_string(__value));
                        }

                        match &self.option {
                            ::std::option::Option::Some(__value) => {
                                __builder.insert("option", g::<T>(__value));
                            }
                            ::std::option::Option::None => {
                                __builder.remove("option");
                            }
                        }

                        if self.string == __default.string {
                            __builder.remove("string");
                        } else {
                            __builder.insert("string", h::<T>(&self.string));
                        }
                    }
                }
            },
        );

        test_ok(
            syn::parse_quote! {
                #[g1_url(insert_default)]
                struct Foo {}
            },
            quote::quote! {
                impl ::g1_url::UpdateQuery for Foo {
                    fn update_query<'update_query: 'query_builder, 'query_builder>(
                        &'update_query self,
                        __builder: &mut ::g1_url::QueryBuilder<'query_builder>,
                    ) {
                    }
                }
            },
        );
        test_ok(
            syn::parse_quote! {
                struct Foo {}
            },
            quote::quote! {
                impl ::g1_url::UpdateQuery for Foo {
                    fn update_query<'update_query: 'query_builder, 'query_builder>(
                        &'update_query self,
                        __builder: &mut ::g1_url::QueryBuilder<'query_builder>,
                    ) {
                    }
                }
            },
        );
    }
}
