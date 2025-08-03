use proc_macro2::TokenStream;

use super::{Codegen, Method};

impl Codegen {
    pub(super) fn generate_message(&self) -> Option<TokenStream> {
        // This is generally intended for this actor to implement another actor's interface (and
        // thus should not generate its own message type).
        if self.message.skip {
            return None;
        }

        if self.is_message_empty() {
            return None;
        }

        let visibility = self.message.visibility();

        let message_type_name = &self.message_type_name;
        let (impl_generics, _, where_clause) = self.actor.exposed.split_for_impl();

        let variants = self
            .actor
            .methods
            .iter()
            .map(Method::generate_message_variant);

        Some(quote::quote! {
            #[allow(non_camel_case_types)]
            #visibility enum #message_type_name #impl_generics #where_clause {
                #(#variants,)*
            }
        })
    }

    pub(super) fn generate_message_queue_recv_field_decl(&self) -> Option<TokenStream> {
        self.generate_message_queue_field_decl("Receiver")
    }

    pub(super) fn generate_message_queue_send_field_decl(&self) -> Option<TokenStream> {
        self.generate_message_queue_field_decl("Sender")
    }

    fn generate_message_queue_field_decl(&self, channel: &str) -> Option<TokenStream> {
        (!self.is_message_empty()).then(|| {
            let message_queue_name = &self.message_queue_name;

            let channel = quote::format_ident!("{channel}");
            let message_type_name = &self.message_type_name;
            let (_, type_generics, _) = self.actor.exposed.split_for_impl();

            quote::quote! {
                #message_queue_name: ::g1_actor::tokio::sync::mpsc::#channel<#message_type_name #type_generics>,
            }
        })
    }

    pub(super) fn generate_message_queue_field(&self) -> Option<TokenStream> {
        (!self.is_message_empty()).then(|| {
            let message_queue_name = &self.message_queue_name;
            quote::quote!(#message_queue_name,)
        })
    }

    pub(super) fn generate_make_message_queue(
        &self,
        buffer: usize,
    ) -> Option<(TokenStream, TokenStream, TokenStream)> {
        (!self.is_message_empty()).then(|| {
            let recv = quote::format_ident!("__message_queue_recv");
            let send = quote::format_ident!("__message_queue_send");
            (
                quote::quote! { let (#send, #recv) = ::g1_actor::tokio::sync::mpsc::channel(#buffer); },
                quote::quote!(#recv,),
                quote::quote!(#send,),
            )
        })
    }
}

impl Method {
    fn generate_message_variant(&self) -> TokenStream {
        let name = &self.name;
        let arg_types = &self.arg_types;
        let ret_type = &self.ret_type;
        quote::quote!(#name((#(#arg_types,)*), ::g1_actor::tokio::sync::oneshot::Sender<#ret_type>))
    }
}

#[cfg(test)]
mod tests {
    use crate::testing::assert_ts_eq;

    use super::*;

    #[test]
    fn generate_message() {
        assert!(
            Codegen::new_mock(quote::quote!(), &syn::parse_quote! { impl Foo {} })
                .generate_message()
                .is_none(),
        );

        let input = syn::parse_quote! {
            impl<T, const N: usize> Foo<N, T>
            where
                T: Display,
            {
                #[method()]
                fn f(&self) {}

                #[method()]
                fn g(_: [T; N]) -> Vec<T> {}
            }
        };
        assert_ts_eq(
            Codegen::new_mock(quote::quote!(), &input)
                .generate_message()
                .unwrap(),
            quote::quote! {
                #[allow(non_camel_case_types)]
                enum FooMessage<T, const N: usize>
                where
                    T: Display
                {
                    f((), ::g1_actor::tokio::sync::oneshot::Sender<()>),
                    g(([T; N],), ::g1_actor::tokio::sync::oneshot::Sender<Vec<T> >),
                }
            },
        );
        assert!(
            Codegen::new_mock(quote::quote!(message(skip)), &input)
                .generate_message()
                .is_none(),
        );
        assert_ts_eq(
            Codegen::new_mock(quote::quote!(message(pub, Spam)), &input)
                .generate_message()
                .unwrap(),
            quote::quote! {
                #[allow(non_camel_case_types)]
                pub enum Spam<T, const N: usize>
                where
                    T: Display
                {
                    f((), ::g1_actor::tokio::sync::oneshot::Sender<()>),
                    g(([T; N],), ::g1_actor::tokio::sync::oneshot::Sender<Vec<T> >),
                }
            },
        );

        assert_ts_eq(
            Codegen::new_mock(
                quote::quote!(message(name = spam_egg)),
                &syn::parse_quote! {
                    impl<T> Foo<T> {
                        #[method(return { let x: (A, B) = x?; })]
                        fn f(_: X, _: Y) -> Z {}
                    }
                },
            )
            .generate_message()
            .unwrap(),
            quote::quote! {
                #[allow(non_camel_case_types)]
                enum spam_egg {
                    f((X, Y,), ::g1_actor::tokio::sync::oneshot::Sender<(A, B)>),
                }
            },
        );
    }
}
