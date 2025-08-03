use syn::{Attribute, Error, ImplItem, ItemImpl};

use crate::actor::{ActorArgs, Loop};
use crate::arg::Args;
use crate::arg_parse::parse_args_from;
use crate::attr;

use super::arg::{react, ret_type, ret_value};

fn match_loop_attr_path(attr: &Attribute) -> bool {
    attr::match_path(attr, &["g1_actor", "actor", "loop_"])
        // Make a special case for `actor::loop_`.
        || attr::exact_match_path(attr, &["actor", "loop_"])
}

impl ActorArgs {
    pub(crate) fn parse_from(&mut self, input: &ItemImpl) -> Result<(), Error> {
        for item in &input.items {
            self.loop_.parse_from(item)?;
        }
        Ok(())
    }

    pub(crate) fn clear_annotations(input: &mut ItemImpl) {
        input.items.iter_mut().for_each(Loop::clear_annotations);
    }
}

impl Loop {
    pub(crate) fn parse_from(&mut self, input: &ImplItem) -> Result<(), Error> {
        let ImplItem::Fn(func) = input else {
            return Ok(());
        };
        for attr in &func.attrs {
            if !match_loop_attr_path(attr) {
                continue;
            }
            let args = attr.parse_args_with(Args::parse_terminated)?;
            let mut react = None;
            parse_args_from!(
                {
                    react: react,
                    ret_type: self.ret_type,
                    ret_value: self.ret_value,
                } = args
            );
            self.reacts.extend(react);
        }
        Ok(())
    }

    pub(crate) fn clear_annotations(input: &mut ImplItem) {
        if let ImplItem::Fn(func) = input {
            func.attrs.retain_mut(|attr| !match_loop_attr_path(attr));
        }
    }
}

#[cfg(test)]
mod tests {
    use crate::testing::{assert_err, assert_ok, replace};

    use super::*;

    #[test]
    fn parse_from() {
        let default = ActorArgs::default();
        let mut args = default.clone();
        assert_ok(
            args.parse_from(&syn::parse_quote! {
                impl Foo {
                    #[::g1_actor::actor::loop_(return self.f())]
                    fn f() {}

                    #[g1_actor::actor::loop_(react = { let x = g(); })]
                    fn g() {}

                    #[actor::loop_(react = { let y = h(); })]
                    fn h() {}

                    #[loop_(type Result<(), Error>)]
                    fn i() {}
                }
            }),
            (),
        );
        assert_eq!(
            args,
            replace!(
                default =>
                .loop_.reacts = vec![
                    (
                        syn::parse_quote!(x),
                        syn::parse_quote!(g()),
                        syn::parse_quote!({}),
                    ),
                    (
                        syn::parse_quote!(y),
                        syn::parse_quote!(h()),
                        syn::parse_quote!({}),
                    ),
                ],
                .loop_.ret_type = Some(syn::parse_quote!(Result<(), Error>)),
                .loop_.ret_value = Some(syn::parse_quote!(self.f())),
            ),
        );

        assert_err(
            args.clone().parse_from(&syn::parse_quote! {
                impl Foo {
                    #[loop_(type Result<(), Error>)]
                    fn f() {}
                }
            }),
            "duplicated argument",
        );
        assert_err(
            args.clone().parse_from(&syn::parse_quote! {
                impl Foo {
                    #[loop_(return self.f())]
                    fn f() {}
                }
            }),
            "duplicated argument",
        );

        assert_err(
            args.clone().parse_from(&syn::parse_quote! {
                impl Foo {
                    #[loop_(pub)]
                    fn f() {}
                }
            }),
            "unknown argument",
        );
    }

    #[test]
    fn clear_annotations() {
        let mut input = syn::parse_quote! {
            impl Foo {
                #[foo]
                fn f() {}

                #[bar]
                #[::g1_actor::actor::loop_()]
                #[g1_actor::actor::loop_()]
                #[actor::loop_()]
                #[loop_()]
                #[::actor::loop_()] // Not matched.
                fn g() {}
            }
        };
        ActorArgs::clear_annotations(&mut input);
        assert_eq!(
            input,
            syn::parse_quote! {
                impl Foo {
                    #[foo]
                    fn f() {}

                    #[bar]
                    #[::actor::loop_()]
                    fn g() {}
                }
            },
        );
    }
}
