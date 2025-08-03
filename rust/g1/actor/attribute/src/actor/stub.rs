use proc_macro2::TokenStream;

use super::{Codegen, Method};

impl Codegen {
    pub(super) fn generate_stub(&self) -> Option<TokenStream> {
        // This is generally intended for this actor to implement another actor's interface (and
        // thus should not generate its own stub type).
        if self.stub.skip {
            return None;
        }

        // If `struct Stub` is not generated, `impl Stub` should not be generated either; however,
        // the opposite is not true.
        let stub_type = self.generate_stub_type()?;

        let impl_stub = self.generate_impl_stub();

        Some(quote::quote! {
            #stub_type
            #impl_stub
        })
    }

    fn generate_stub_type(&self) -> Option<TokenStream> {
        if self.is_stub_zero_sized() {
            return None;
        }

        let visibility = self.stub.visibility();

        let stub_type_name = &self.stub_type_name;
        let (impl_generics, _, where_clause) = self.actor.exposed.split_for_impl();

        let derive = self.stub.derive.as_ref().unwrap_or(&self.stub_derive);
        let derive = (!derive.is_empty()).then(|| quote::quote!(#[derive(#(#derive),*)]));

        let message_queue_field_decl = self.generate_message_queue_send_field_decl();

        let fields = &self.stub.fields;

        Some(quote::quote! {
            #derive
            #visibility struct #stub_type_name #impl_generics #where_clause {
                #message_queue_field_decl
                #fields
            }
        })
    }

    fn generate_impl_stub(&self) -> Option<TokenStream> {
        let spawn_func = self.generate_stub_spawn_func();
        let new_func = self.generate_stub_new_func();

        if spawn_func.is_none() && new_func.is_none() && self.is_message_empty() {
            return None;
        }

        let stub_type_name = &self.stub_type_name;
        let (impl_generics, type_generics, where_clause) = self.actor.exposed.split_for_impl();

        let methods = self
            .actor
            .methods
            .iter()
            .map(|method| method.generate_stub_method(self));

        Some(quote::quote! {
            impl #impl_generics #stub_type_name #type_generics #where_clause {
                #spawn_func
                #new_func
                #(#methods)*
            }
        })
    }

    fn generate_stub_spawn_func(&self) -> Option<TokenStream> {
        if self.stub.spawn.skip {
            return None;
        }

        if self.is_stub_zero_sized() {
            return None;
        }

        let visibility = self.stub.spawn.visibility();

        let name = self
            .stub
            .spawn
            .name
            .as_ref()
            .unwrap_or(&self.spawn_func_name);
        let (impl_generics, _, where_clause) = self.actor.not_exposed.split_for_impl();

        let new_func_arg_decls = self.generate_stub_new_func_arg_decls();
        let new_func_args = self.generate_stub_new_func_args();

        let actor_type = &self.actor.type_;
        let actor_name = &self.actor_name;

        let loop_ret_type = self
            .loop_
            .ret_type
            .clone()
            .unwrap_or_else(|| syn::parse_quote!(()));

        // TODO: Make the queue capacity configurable.
        let (make_message_queue, message_queue_recv, message_queue_send) = self
            .generate_make_message_queue(16)
            .map_or((None, None, None), |(a, b, c)| (Some(a), Some(b), Some(c)));

        let stub_new_func_name = self.stub.new.name.as_ref().unwrap_or(&self.new_func_name);

        let loop_type_name = &self.loop_type_name;
        let loop_new_func_name = self.loop_.new.name.as_ref().unwrap_or(&self.new_func_name);

        // We do not look up `self.loop_.run.name`.  This is intended to allow the user to rename
        // the generated `run` function and write their own `run` function to be called here.
        let loop_run_func_name = &self.run_func_name;

        Some(quote::quote! {
            #visibility fn #name #impl_generics (
                #(#new_func_arg_decls)*
                #actor_name: #actor_type,
            ) -> (Self, ::g1_actor::g1_tokio::task::JoinGuard<#loop_ret_type>)
            #where_clause
            {
                #make_message_queue
                (
                    Self::#stub_new_func_name(#message_queue_send #(#new_func_args)*),
                    ::g1_actor::g1_tokio::task::JoinGuard::spawn(move |__cancel| {
                        let mut __loop = #loop_type_name::#loop_new_func_name(
                            __cancel,
                            #message_queue_recv
                            #actor_name,
                        );
                        async move { __loop.#loop_run_func_name().await }
                    }),
                )
            }
        })
    }

    fn generate_stub_new_func(&self) -> Option<TokenStream> {
        if self.stub.new.skip {
            return None;
        }

        if self.is_stub_zero_sized() {
            return None;
        }

        let visibility = self.stub.new.visibility();

        let name = self.stub.new.name.as_ref().unwrap_or(&self.new_func_name);

        let message_queue_arg_decl = self.generate_message_queue_send_field_decl();
        let message_queue_arg = self.generate_message_queue_field();

        let new_func_arg_decls = self.generate_stub_new_func_arg_decls();
        let new_func_args = self.generate_stub_new_func_args();

        Some(quote::quote! {
            #visibility fn #name(#message_queue_arg_decl #(#new_func_arg_decls)*) -> Self {
                Self {
                    #message_queue_arg
                    #(#new_func_args)*
                }
            }
        })
    }

    fn generate_stub_new_func_arg_decls(&self) -> impl Iterator<Item = TokenStream> {
        self.stub.fields.iter().map(|field| {
            let type_ = &field.ty;
            let name = &field.ident;
            quote::quote!(#name: #type_,)
        })
    }

    fn generate_stub_new_func_args(&self) -> impl Iterator<Item = TokenStream> {
        self.stub.fields.iter().map(|field| {
            let name = &field.ident;
            quote::quote!(#name,)
        })
    }
}

impl Method {
    fn generate_stub_method(&self, codegen: &Codegen) -> TokenStream {
        let visibility = self.visibility();

        let name = &self.name;

        let arg_decls = self
            .arg_pairs()
            .map(|(name, type_)| quote::quote!(#name: #type_));

        // Result<ret_type, Option<arg_types>>
        let ret_type = &self.ret_type;
        let arg_types = &self.arg_types;

        let message_type_name = &codegen.message_type_name;
        let arg_names = &self.arg_names;

        quote::quote! {
            #visibility async fn #name(
                &self, #(#arg_decls,)*
            ) -> ::std::result::Result<#ret_type, ::std::option::Option<(#(#arg_types,)*)>> {
                let (__ret_send, __ret_recv) = ::g1_actor::tokio::sync::oneshot::channel();
                self.__message_queue
                    .send(#message_type_name::#name((#(#arg_names,)*), __ret_send))
                    .await
                    .map_err(|::g1_actor::tokio::sync::mpsc::error::SendError(__message)| match __message {
                        #message_type_name::#name(__args, _) => ::std::option::Option::Some(__args),
                        _ => ::std::unreachable!(),
                    })?;
                __ret_recv.await.map_err(|_| ::std::option::Option::None)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use crate::testing::assert_ts_eq;

    use super::*;

    #[test]
    fn generate_stub() {
        assert!(
            Codegen::new_mock(quote::quote!(), &syn::parse_quote! { impl Foo {} })
                .generate_stub()
                .is_none(),
        );

        assert!(
            Codegen::new_mock(
                quote::quote!(stub(skip)),
                &syn::parse_quote! {
                    impl Foo {
                        #[method()]
                        fn f() {}
                    }
                },
            )
            .generate_stub()
            .is_none(),
        );
    }

    #[test]
    fn generate_stub_type() {
        assert!(
            Codegen::new_mock(quote::quote!(), &syn::parse_quote! { impl Foo {} })
                .generate_stub_type()
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
                .generate_stub_type()
                .unwrap(),
            quote::quote! {
                #[derive(Clone, Debug)]
                struct FooStub<T, const N: usize>
                where
                    T: Display
                {
                    __message_queue: ::g1_actor::tokio::sync::mpsc::Sender<FooMessage<T, N> >,
                }
            },
        );
        assert_ts_eq(
            Codegen::new_mock(
                quote::quote!(
                    stub(
                        pub,
                        Spam,
                        struct {
                            #[foo]
                            pub x: u8,
                            y: u16
                        },
                    ),
                    message(Egg),
                ),
                &input,
            )
            .generate_stub_type()
            .unwrap(),
            quote::quote! {
                #[derive(Clone, Debug)]
                pub struct Spam<T, const N: usize>
                where
                    T: Display
                {
                    __message_queue: ::g1_actor::tokio::sync::mpsc::Sender<Egg<T, N> >,
                    #[foo]
                    pub x: u8,
                    y: u16,
                }
            },
        );

        assert_ts_eq(
            Codegen::new_mock(
                quote::quote!(stub(pub(in super), name = skip, struct { x: u8 })),
                &syn::parse_quote! { impl<T, const N: usize> Foo<N, T> where T: Display {} },
            )
            .generate_stub_type()
            .unwrap(),
            quote::quote! {
                #[derive(Clone, Debug)]
                pub(in super) struct skip {
                    x: u8,
                }
            },
        );

        assert_ts_eq(
            Codegen::new_mock(
                quote::quote!(stub(derive(), struct { x: u8 })),
                &syn::parse_quote! { impl Foo {} },
            )
            .generate_stub_type()
            .unwrap(),
            quote::quote! {
                struct FooStub {
                    x: u8,
                }
            },
        );
        assert_ts_eq(
            Codegen::new_mock(
                quote::quote!(stub(derive(X, Y, Z), struct { x: u8 })),
                &syn::parse_quote! { impl Foo {} },
            )
            .generate_stub_type()
            .unwrap(),
            quote::quote! {
                #[derive(X, Y, Z)]
                struct FooStub {
                    x: u8,
                }
            },
        );
    }

    #[test]
    fn generate_impl_stub() {
        assert!(
            Codegen::new_mock(quote::quote!(), &syn::parse_quote! { impl Foo {} })
                .generate_impl_stub()
                .is_none(),
        );

        assert_ts_eq(
            Codegen::new_mock(
                quote::quote!(
                    stub(
                        struct {
                            #[foo]
                            pub x: u8
                        },
                        spawn(pub, my_spawn),
                        new(pub, my_new),
                    ),
                    loop_(run(run_inner)),
                ),
                &syn::parse_quote! {
                    impl<T, const N: usize, U: Debug> Foo<U, N, T>
                    where
                        U: PartialEq,
                        T: Display,
                    {
                        #[method(pub)]
                        fn f(&self) {}

                        #[method(return { let x: X = x; })]
                        fn g(_: [T; N]) -> Vec<T> {}
                    }
                },
            )
            .generate_impl_stub()
            .unwrap(),
            quote::quote! {
                impl<T, const N: usize> FooStub<T, N>
                where
                    T: Display
                {
                    pub fn my_spawn<U: Debug>(x: u8, __actor: Foo<U, N, T>,) -> (Self, ::g1_actor::g1_tokio::task::JoinGuard<()>)
                    where
                       U: PartialEq
                    {
                        let (__message_queue_send, __message_queue_recv) = ::g1_actor::tokio::sync::mpsc::channel(16usize);
                        (
                            Self::my_new(__message_queue_send, x,),
                            ::g1_actor::g1_tokio::task::JoinGuard::spawn(move |__cancel| {
                                let mut __loop = FooLoop::new(
                                    __cancel,
                                    __message_queue_recv,
                                    __actor,
                                );
                                async move { __loop.run().await }
                            }),
                        )
                    }

                    pub fn my_new(__message_queue: ::g1_actor::tokio::sync::mpsc::Sender<FooMessage<T, N> >, x: u8,) -> Self {
                        Self { __message_queue, x, }
                    }

                    pub async fn f(&self, ) -> ::std::result::Result<(), ::std::option::Option<()>> {
                        let (__ret_send, __ret_recv) = ::g1_actor::tokio::sync::oneshot::channel();
                        self.__message_queue
                            .send(FooMessage::f((), __ret_send))
                            .await
                            .map_err(|::g1_actor::tokio::sync::mpsc::error::SendError(__message)| match __message {
                                FooMessage::f(__args, _) => ::std::option::Option::Some(__args),
                                _ => ::std::unreachable!(),
                            })?;
                        __ret_recv.await.map_err(|_| ::std::option::Option::None)
                    }

                    async fn g(&self, __arg_0: [T; N],) -> ::std::result::Result<X, ::std::option::Option<([T; N],)>> {
                        let (__ret_send, __ret_recv) = ::g1_actor::tokio::sync::oneshot::channel();
                        self.__message_queue
                            .send(FooMessage::g((__arg_0,), __ret_send))
                            .await
                            .map_err(|::g1_actor::tokio::sync::mpsc::error::SendError(__message)| match __message {
                                FooMessage::g(__args, _) => ::std::option::Option::Some(__args),
                                _ => ::std::unreachable!(),
                            })?;
                        __ret_recv.await.map_err(|_| ::std::option::Option::None)
                    }
                }
            },
        );

        assert_ts_eq(
            Codegen::new_mock(
                quote::quote!(stub(spawn(skip), new(skip))),
                &syn::parse_quote! {
                    impl Foo {
                        #[method()]
                        fn f(&self) {}
                    }
                },
            )
            .generate_impl_stub()
            .unwrap(),
            quote::quote! {
                impl FooStub {
                    async fn f(&self,) -> ::std::result::Result<(), ::std::option::Option<()>> {
                        let (__ret_send, __ret_recv) = ::g1_actor::tokio::sync::oneshot::channel();
                        self.__message_queue
                            .send(FooMessage::f((), __ret_send))
                            .await
                            .map_err(|::g1_actor::tokio::sync::mpsc::error::SendError(__message)| match __message {
                                FooMessage::f(__args, _) => ::std::option::Option::Some(__args),
                                _ => ::std::unreachable!(),
                            })?;
                        __ret_recv.await.map_err(|_| ::std::option::Option::None)
                    }
                }
            },
        );
    }
}
