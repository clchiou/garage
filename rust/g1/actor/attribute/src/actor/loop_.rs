use proc_macro2::TokenStream;
use syn::visit_mut::VisitMut;

use crate::replace;

use super::{Codegen, Method};

impl Codegen {
    pub(super) fn generate_loop(&self) -> Option<TokenStream> {
        if self.loop_.skip {
            return None;
        }

        // If `struct Loop` is not generated, `impl Loop` should not be generated either; however,
        // the opposite is not true.
        let loop_type = self.generate_loop_type()?;

        let impl_loop = self.generate_impl_loop();

        Some(quote::quote! {
            #loop_type
            #impl_loop
        })
    }

    fn generate_loop_type(&self) -> Option<TokenStream> {
        if self.is_loop_trivial() {
            return None;
        }

        let visibility = self.loop_.visibility();

        let loop_type_name = &self.loop_type_name;
        let (impl_generics, _, where_clause) = self.actor.generics.split_for_impl();

        let message_queue_field_decl = self.generate_message_queue_recv_field_decl();

        let actor_type = &self.actor.type_;
        let actor_name = &self.actor_name;

        Some(quote::quote! {
            #visibility struct #loop_type_name #impl_generics #where_clause {
                __cancel: ::g1_actor::g1_tokio::task::Cancel,
                #message_queue_field_decl
                #actor_name: #actor_type,
            }
        })
    }

    fn generate_impl_loop(&self) -> Option<TokenStream> {
        let new_func = self.generate_loop_new_func();
        let run_func = self.generate_loop_run_func();

        if new_func.is_none() && run_func.is_none() {
            return None;
        }

        let loop_type_name = &self.loop_type_name;
        let (impl_generics, type_generics, where_clause) = self.actor.generics.split_for_impl();

        Some(quote::quote! {
            impl #impl_generics #loop_type_name #type_generics #where_clause {
                #new_func
                #run_func
            }
        })
    }

    fn generate_loop_new_func(&self) -> Option<TokenStream> {
        if self.loop_.new.skip {
            return None;
        }

        if self.is_loop_trivial() {
            return None;
        }

        let visibility = self.loop_.new.visibility();

        let name = self.loop_.new.name.as_ref().unwrap_or(&self.new_func_name);

        let message_queue_arg_decl = self.generate_message_queue_recv_field_decl();
        let message_queue_arg = self.generate_message_queue_field();

        let actor_type = &self.actor.type_;
        let actor_name = &self.actor_name;

        Some(quote::quote! {
            #visibility fn #name(
                __cancel: ::g1_actor::g1_tokio::task::Cancel,
                #message_queue_arg_decl
                #actor_name: #actor_type,
            ) -> Self {
                Self {
                    __cancel,
                    #message_queue_arg
                    #actor_name,
                }
            }
        })
    }

    fn generate_loop_run_func(&self) -> Option<TokenStream> {
        if self.loop_.run.skip {
            return None;
        }

        if self.is_loop_trivial() {
            return None;
        }

        let visibility = self.loop_.run.visibility();

        let name = self.loop_.run.name.as_ref().unwrap_or(&self.run_func_name);

        let ret_type = self
            .loop_
            .ret_type
            .as_ref()
            .map(|ret_type| quote::quote!(-> #ret_type));

        let mut ret_value = self.loop_.ret_value.clone();
        if let Some(ret_value) = ret_value.as_mut() {
            self.expr_replace_self_keyword(ret_value);
        }

        let message_queue_destructure = self.generate_message_queue_field();
        let actor_name = &self.actor_name;

        let select_message_branch = (!self.is_message_empty()).then(|| {
            let message_queue_name = &self.message_queue_name;
            let match_arms = self
                .actor
                .methods
                .iter()
                .map(|method| method.generate_loop_match_arm(self));
            if self.loop_.reacts.is_empty() {
                // Special case: `break` when there are no reactors and no more messages.
                quote::quote! {
                    __message = #message_queue_name.recv() => match __message {
                        ::std::option::Option::Some(__message) => match __message {
                            #(#match_arms)*
                        },
                        ::std::option::Option::None => break,
                    },
                }
            } else {
                quote::quote! {
                    ::std::option::Option::Some(__message) = #message_queue_name.recv() => match __message {
                        #(#match_arms)*
                    },
                }
            }
        });

        let select_react_branches =
            self.loop_
                .reacts
                .iter()
                .cloned()
                .map(|(mut pat, mut expr, mut block)| {
                    self.pat_replace_self_keyword(&mut pat);
                    self.expr_replace_self_keyword(&mut expr);
                    self.expr_replace_self_keyword(&mut block);
                    quote::quote!(#pat = #expr => #block)
                });

        Some(quote::quote! {
            #visibility async fn #name(&mut self) #ret_type {
                let Self { __cancel, #message_queue_destructure #actor_name, } = self;
                loop {
                    ::g1_actor::tokio::select! {
                        () = __cancel.wait() => break,
                        #select_message_branch
                        #(#select_react_branches)*
                    }
                }
                #ret_value
            }
        })
    }
}

impl Method {
    fn generate_loop_match_arm(&self, codegen: &Codegen) -> TokenStream {
        let message_type_name = &codegen.message_type_name;
        let name = &self.name;
        let arg_names = &self.arg_names;

        let ret = quote::format_ident!("__ret");

        // ::module::Actor::<T>::method(actor, arg_0, ...).await
        let actor_type_name = &codegen.actor_type_name;
        let args = self
            .has_receiver
            .then_some(&codegen.actor_name)
            .into_iter()
            .chain(&self.arg_names);
        let await_ = self.asyncness.then(|| quote::quote!(.await));

        let ret_expr = self.ret_expr.as_ref().map(|(var, ret_expr)| {
            let mut ret_expr = ret_expr.clone();
            codegen.expr_replace_self_keyword(&mut ret_expr);
            replace::ident_replacer(var, || ret.clone()).visit_expr_mut(&mut ret_expr);
            quote::quote!(let #ret = #ret_expr;)
        });

        quote::quote! {
            #message_type_name::#name((#(#arg_names,)*), __ret_send) => {
                let #ret = #actor_type_name::#name(#(#args),*)#await_;
                #ret_expr
                let _ = __ret_send.send(#ret);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use crate::testing::assert_ts_eq;

    use super::*;

    #[test]
    fn generate_loop() {
        assert!(
            Codegen::new_mock(quote::quote!(), &syn::parse_quote! { impl Foo {} })
                .generate_loop()
                .is_none(),
        );

        assert!(
            Codegen::new_mock(
                quote::quote!(loop_(skip)),
                &syn::parse_quote! {
                    impl Foo {
                        #[method()]
                        fn f() {}
                    }
                },
            )
            .generate_loop()
            .is_none(),
        );
    }

    #[test]
    fn generate_loop_type() {
        assert!(
            Codegen::new_mock(quote::quote!(), &syn::parse_quote! { impl Foo {} })
                .generate_loop_type()
                .is_none(),
        );

        assert_ts_eq(
            Codegen::new_mock(
                quote::quote!(loop_(pub(crate), MyFooLoop)),
                &syn::parse_quote! {
                    impl<A, const B: usize, C> ::module::Foo<C, A, B> {
                        #[method()]
                        fn f(_: A) {}
                    }
                },
            )
            .generate_loop_type()
            .unwrap(),
            quote::quote! {
                pub(crate) struct MyFooLoop<A, const B: usize, C> {
                    __cancel: ::g1_actor::g1_tokio::task::Cancel,
                    __message_queue: ::g1_actor::tokio::sync::mpsc::Receiver<FooMessage<A> >,
                    __actor: ::module::Foo<C, A, B>,
                }
            },
        );

        assert_ts_eq(
            Codegen::new_mock(
                quote::quote!(loop_(
                    react = {
                        let x = f();
                    }
                )),
                &syn::parse_quote! { impl Foo {} },
            )
            .generate_loop_type()
            .unwrap(),
            quote::quote! {
                struct FooLoop {
                    __cancel: ::g1_actor::g1_tokio::task::Cancel,
                    __actor: Foo,
                }
            },
        );
    }

    #[test]
    fn generate_impl_loop() {
        assert!(
            Codegen::new_mock(quote::quote!(), &syn::parse_quote! { impl Foo {} })
                .generate_impl_loop()
                .is_none(),
        );

        let input = syn::parse_quote! {
            impl<A, const B: usize, C> ::module::Foo<C, A, B> {
                #[method(return { let x: String = x?; })]
                async fn f(&self, _: A) -> Result<String, Error> {}
            }
        };
        assert_ts_eq(
            Codegen::new_mock(quote::quote!(), &input)
                .generate_impl_loop()
                .unwrap(),
            quote::quote! {
                impl<A, const B: usize, C> FooLoop<A, B, C> {
                    fn new(
                        __cancel: ::g1_actor::g1_tokio::task::Cancel,
                        __message_queue: ::g1_actor::tokio::sync::mpsc::Receiver<FooMessage<A> >,
                        __actor: ::module::Foo<C, A, B>,
                    ) -> Self {
                        Self {
                            __cancel,
                            __message_queue,
                            __actor,
                        }
                    }

                    async fn run(&mut self) {
                        let Self { __cancel, __message_queue, __actor, } = self;
                        loop {
                            ::g1_actor::tokio::select! {
                                () = __cancel.wait() => break,
                                __message = __message_queue.recv() => match __message {
                                    ::std::option::Option::Some(__message) => match __message {
                                        FooMessage::f((__arg_0,), __ret_send) => {
                                            let __ret = ::module::Foo::<C, A, B>::f(__actor, __arg_0).await;
                                            let __ret = __ret?;
                                            let _ = __ret_send.send(__ret);
                                        }
                                    },
                                    ::std::option::Option::None => break,
                                },
                            }
                        }
                    }
                }
            },
        );
        assert_ts_eq(
            Codegen::new_mock(
                quote::quote!(loop_(
                    react = { let Self::Spam(_) = Self::wait_for(&self.timer); },
                    react = { let Some(x) = self.timer.wait(); x? },
                    type Result<(), Error>,
                    return Ok(()),
                    new(skip),
                )),
                &input,
            )
            .generate_impl_loop()
            .unwrap(),
            quote::quote! {
                impl<A, const B: usize, C> FooLoop<A, B, C> {
                    async fn run(&mut self) -> Result<(), Error> {
                        let Self { __cancel, __message_queue, __actor, } = self;
                        loop {
                            ::g1_actor::tokio::select! {
                                () = __cancel.wait() => break,
                                ::std::option::Option::Some(__message) = __message_queue.recv() => match __message {
                                    FooMessage::f((__arg_0,), __ret_send) => {
                                        let __ret = ::module::Foo::<C, A, B>::f(__actor, __arg_0).await;
                                        let __ret = __ret?;
                                        let _ = __ret_send.send(__ret);
                                    }
                                },
                                ::module::Foo::Spam(_) = ::module::Foo::<C, A, B>::wait_for(&__actor.timer) => {}
                                Some(x) = __actor.timer.wait() => { x? }
                            }
                        }
                        Ok(())
                    }
                }
            },
        );

        assert_ts_eq(
            Codegen::new_mock(
                quote::quote!(loop_(
                    react = {
                        let Some(x) = self.timer.wait();
                        x?
                    },
                    new(skip),
                    run(pub(in super), run_inner),
                )),
                &syn::parse_quote! { impl Foo {} },
            )
            .generate_impl_loop()
            .unwrap(),
            quote::quote! {
                impl FooLoop {
                    pub(in super) async fn run_inner(&mut self) {
                        let Self { __cancel, __actor, } = self;
                        loop {
                            ::g1_actor::tokio::select! {
                                () = __cancel.wait() => break,
                                Some(x) = __actor.timer.wait() => { x? }
                            }
                        }
                    }
                }
            },
        );
    }
}
