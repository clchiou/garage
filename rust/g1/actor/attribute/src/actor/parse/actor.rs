use syn::punctuated::Punctuated;
use syn::spanned::Spanned;
use syn::{
    Attribute, Block, ConstParam, Error, Expr, ExprBlock, FnArg, GenericArgument, GenericParam,
    Generics, Ident, ImplItem, ItemImpl, Lifetime, Local, LocalInit, Pat, PatIdent, PatType,
    PathArguments, Receiver, ReturnType, Stmt, Token, Type, TypeParam, TypePath, Visibility,
    WhereClause, WherePredicate,
};

use crate::actor::{Actor, Method};
use crate::arg::{Arg, ArgValue, Args};
use crate::arg_parse::{parse_args_from, scalar_arg};
use crate::attr;
use crate::error::{ensure, ensure_none};
use crate::generic;

use super::arg::visibility;

fn match_method_attr_path(attr: &Attribute) -> bool {
    attr::match_path(attr, &["g1_actor", "actor", "method"])
        // Make a special case for `actor::method`.
        || attr::exact_match_path(attr, &["actor", "method"])
}

impl Actor {
    pub(crate) fn parse(input: &ItemImpl) -> Result<Self, Error> {
        ensure_none!(
            input.trait_,
            input.trait_.as_ref().unwrap().1.span(),
            "`impl Trait` is not supported",
        );

        ensure!(
            check_actor_type(&input.self_ty),
            input.self_ty.span(),
            "currently only types like `module::Actor<T>` are supported",
        );

        for param in &input.generics.params {
            ensure!(
                !matches!(param, GenericParam::Lifetime(_)),
                param.span(),
                "actor should not have a non-static lifetime parameter",
            );
        }
        ensure!(
            check_actor_type_lifetime(&input.self_ty),
            input.self_ty.span(),
            "actor should not have a non-static lifetime parameter",
        );

        let methods = input
            .items
            .iter()
            .filter_map(|item| Method::try_parse(item).transpose())
            .try_collect::<Vec<_>>()?;

        // Categorize generic parameters into two groups: those that are exposed by the methods and
        // and those that are not.
        let (exposed, not_exposed) = partition(&input.generics, |param| {
            methods.iter().any(|method| method.signature_find(param))
        });

        Ok(Self {
            type_: (*input.self_ty).clone(),

            generics: input.generics.clone(),
            exposed,
            not_exposed,

            methods,
        })
    }

    pub(crate) fn clear_annotations(input: &mut ItemImpl) {
        input.items.iter_mut().for_each(Method::clear_annotations);
    }
}

fn check_actor_type(type_: &Type) -> bool {
    let Type::Path(TypePath { qself: None, path }) = type_ else {
        return false;
    };
    let mut segments = path.segments.iter().rev();
    matches!(
        segments.next().expect("segments").arguments,
        PathArguments::None | PathArguments::AngleBracketed(_),
    ) && segments.all(|segment| segment.arguments.is_none())
}

fn check_actor_type_lifetime(type_: &Type) -> bool {
    fn is_non_static_lifetime(arg: &GenericArgument) -> bool {
        matches!(arg, GenericArgument::Lifetime(Lifetime { ident, .. }) if ident != "static")
    }

    let Type::Path(TypePath { qself: None, path }) = type_ else {
        return false;
    };
    for segment in &path.segments {
        if let PathArguments::AngleBracketed(angle) = &segment.arguments {
            if angle.args.iter().any(is_non_static_lifetime) {
                return false;
            }
        }
    }
    true
}

// NOTE: This function is asymmetrical, favoring the second `Generics` return value.
fn partition<F>(generics: &Generics, mut f: F) -> (Generics, Generics)
where
    F: FnMut(&Ident) -> bool,
{
    let mut t_params = Punctuated::new();
    let mut f_params = Punctuated::new();
    let mut f_param_idents = Vec::new();
    for param in &generics.params {
        match param {
            GenericParam::Type(TypeParam { ident, .. })
            | GenericParam::Const(ConstParam { ident, .. }) => {
                if f(ident) {
                    t_params.push(param.clone());
                } else {
                    f_params.push(param.clone());
                    f_param_idents.push(ident.clone());
                }
            }
            GenericParam::Lifetime(_) => unreachable!(),
        }
    }

    // NOTE: We are biased toward `f_params`: if a predicate contains any generic parameter from
    // `f_params`, it is considered to belong to `f_params`.
    let f_match = |predicate: &&WherePredicate| match predicate {
        WherePredicate::Type(p) => generic::predicate_type_find_any(p, &f_param_idents),
        WherePredicate::Lifetime(_) => unreachable!(),
        _ => unimplemented!(),
    };

    fn make_generics_from_params<F>(
        params: Punctuated<GenericParam, Token![,]>,
        match_predicate: F,
        generics: &Generics,
    ) -> Generics
    where
        F: Fn(&&WherePredicate) -> bool,
    {
        let lt_token = (!params.is_empty()).then_some(generics.lt_token).flatten();
        let gt_token = (!params.is_empty()).then_some(generics.gt_token).flatten();

        let where_clause = generics.where_clause.as_ref().and_then(|where_clause| {
            let predicates = where_clause
                .predicates
                .iter()
                .filter(match_predicate)
                .cloned()
                .collect::<Punctuated<_, _>>();
            (!predicates.is_empty()).then(|| WhereClause {
                where_token: where_clause.where_token,
                predicates,
            })
        });

        Generics {
            lt_token,
            params,
            gt_token,
            where_clause,
        }
    }

    (
        make_generics_from_params(t_params, |p| !f_match(p), generics),
        make_generics_from_params(f_params, f_match, generics),
    )
}

impl Method {
    fn try_parse(input: &ImplItem) -> Result<Option<Self>, Error> {
        let ImplItem::Fn(func) = input else {
            return Ok(None);
        };

        let mut method_attr = MethodAttr::default();
        let mut has_attr = false;
        for attr in &func.attrs {
            if method_attr.try_parse_from(attr)? {
                has_attr = true;
            }
        }
        if !has_attr {
            return Ok(None);
        }
        let MethodAttr {
            visibility,
            ret_expr,
        } = method_attr;
        let (ret_type, ret_expr) =
            ret_expr.map_or((None, None), |(type_, expr)| (Some(type_), Some(expr)));

        ensure!(
            func.sig.generics.params.is_empty(),
            func.sig.generics.span(),
            "generic method is not supported",
        );
        ensure_none!(
            func.sig.variadic,
            func.sig.variadic.span(),
            "variadic method is not supported",
        );

        let has_receiver = match func.sig.receiver() {
            Some(receiver) => {
                ensure!(
                    check_method_receiver(receiver),
                    receiver.span(),
                    "currently only `&self` and `&mut self` are supported",
                );
                true
            }
            None => false,
        };

        let arg_types = func
            .sig
            .inputs
            .iter()
            .filter_map(|arg| match arg {
                FnArg::Typed(PatType { ty, .. }) => Some((**ty).clone()),
                FnArg::Receiver(_) => None,
            })
            .collect::<Vec<_>>();
        let arg_names = (0..arg_types.len())
            .map(|i| quote::format_ident!("__arg_{i}"))
            .collect();

        Ok(Some(Self {
            visibility,

            asyncness: func.sig.asyncness.is_some(),

            name: func.sig.ident.clone(),

            has_receiver,

            arg_types,
            arg_names,

            ret_type: ret_type.unwrap_or_else(|| match &func.sig.output {
                ReturnType::Type(_, ret_type) => (**ret_type).clone(),
                ReturnType::Default => syn::parse_quote!(()),
            }),
            ret_expr,
        }))
    }

    fn signature_find(&self, param: &Ident) -> bool {
        self.arg_types
            .iter()
            .any(|ty| generic::type_find(ty, param))
            || generic::type_find(&self.ret_type, param)
    }

    fn clear_annotations(input: &mut ImplItem) {
        if let ImplItem::Fn(func) = input {
            func.attrs.retain_mut(|attr| !match_method_attr_path(attr));
        }
    }
}

fn check_method_receiver(receiver: &Receiver) -> bool {
    if receiver.reference.is_some() {
        // `&self`
        receiver.colon_token.is_none()
    } else {
        // `self: &Box<Self>`
        receiver.colon_token.is_some() && matches!(*receiver.ty, Type::Reference(_))
    }
}

#[derive(Default)]
struct MethodAttr {
    visibility: Option<Visibility>,
    ret_expr: Option<(Type, (Ident, Expr))>,
}

impl MethodAttr {
    fn try_parse_from(&mut self, attr: &Attribute) -> Result<bool, Error> {
        if !match_method_attr_path(attr) {
            return Ok(false);
        }
        parse_args_from!(
            {
                visibility: self.visibility,
                ret_expr: self.ret_expr,
            } = attr.parse_args_with(Args::parse_terminated)?
        );
        Ok(true)
    }
}

scalar_arg! {
    ret_expr: (Type, (Ident, Expr)) =
    Arg::ValueOnly(ArgValue::Return(token, block)) => (token.span(), parse_ret_expr(block)?),
}

fn parse_ret_expr(block: Expr) -> Result<(Type, (Ident, Expr)), Error> {
    let span = block.span();
    let error = || Error::new(span, "expect `{ let <ident>: <type> = <expr>; }`");

    let Expr::Block(ExprBlock {
        block: Block { mut stmts, .. },
        ..
    }) = block
    else {
        return Err(error());
    };

    if stmts.len() != 1 {
        return Err(error());
    }

    let Stmt::Local(Local {
        pat,
        init:
            Some(LocalInit {
                expr,
                diverge: None,
                ..
            }),
        ..
    }) = stmts.remove(0)
    else {
        return Err(error());
    };

    let Pat::Type(PatType { pat, ty, .. }) = pat else {
        return Err(error());
    };

    let Pat::Ident(PatIdent {
        by_ref: None,
        mutability: None,
        ident,
        subpat: None,
        ..
    }) = Box::into_inner(pat)
    else {
        return Err(error());
    };

    Ok((Box::into_inner(ty), (ident, Box::into_inner(expr))))
}

#[cfg(test)]
mod tests {
    use crate::testing::{assert_err, assert_ok, i, replace};

    use super::*;

    fn g(mut generics: Generics, where_clause: WhereClause) -> Generics {
        generics.where_clause = Some(where_clause);
        generics
    }

    #[test]
    fn actor_parse() {
        let actor = Actor {
            type_: syn::parse_quote!(Foo),
            generics: Default::default(),
            exposed: Default::default(),
            not_exposed: Default::default(),
            methods: vec![],
        };
        assert_ok(
            Actor::parse(&syn::parse_quote! {
                impl Foo {}
            }),
            actor.clone(),
        );

        let method = Method {
            visibility: None,
            asyncness: false,
            name: i("f"),
            has_receiver: false,
            arg_types: vec![],
            arg_names: vec![],
            ret_type: syn::parse_quote!(()),
            ret_expr: None,
        };
        assert_ok(
            Actor::parse(&syn::parse_quote! {
                impl<A, const N: usize, B: Debug> Foo<B, A, N>
                where
                    A: PartialEq
                {
                    #[method()]
                    fn f(_: [A; N]) -> B {}
                }
            }),
            Actor {
                type_: syn::parse_quote!(Foo<B, A, N>),
                generics: g(
                    syn::parse_quote!(<A, const N: usize, B: Debug>), // No trailing comma.
                    syn::parse_quote!(where A: PartialEq),            // No trailing comma.
                ),
                exposed: g(
                    syn::parse_quote!(<A, const N: usize, B: Debug>), // No trailing comma.
                    syn::parse_quote!(where A: PartialEq),            // No trailing comma.
                ),
                not_exposed: Default::default(),
                methods: vec![replace!(
                    method =>
                    .arg_types = vec![syn::parse_quote!([A; N])],
                    .arg_names = vec![i("__arg_0")],
                    .ret_type = syn::parse_quote!(B),
                )],
            },
        );
        assert_ok(
            Actor::parse(&syn::parse_quote! {
                impl<A, const N: usize, B: Debug,> Foo<B, A, N>
                where
                    A: PartialEq,
                {
                    #[method()]
                    fn f(_: String) -> usize {}
                }
            }),
            Actor {
                type_: syn::parse_quote!(Foo<B, A, N>),
                generics: g(
                    syn::parse_quote!(<A, const N: usize, B: Debug,>), // Trailing comma.
                    syn::parse_quote!(where A: PartialEq,),            // Trailing comma.
                ),
                exposed: Default::default(),
                not_exposed: g(
                    syn::parse_quote!(<A, const N: usize, B: Debug>), // No trailing comma.
                    syn::parse_quote!(where A: PartialEq),            // No trailing comma.
                ),
                methods: vec![replace!(
                    method =>
                    .arg_types = vec![syn::parse_quote!(String)],
                    .arg_names = vec![i("__arg_0")],
                    .ret_type = syn::parse_quote!(usize),
                )],
            },
        );
        assert_ok(
            Actor::parse(&syn::parse_quote! {
                impl<A, B> Foo<A, B>
                where
                    A: From<B>,
                {
                    #[method()]
                    fn f(_: A) {}
                }
            }),
            Actor {
                type_: syn::parse_quote!(Foo<A, B>),
                generics: g(
                    syn::parse_quote!(<A, B>),
                    syn::parse_quote!(where A: From<B>,),
                ),
                exposed: syn::parse_quote!(<A>),
                not_exposed: g(syn::parse_quote!(<B>), syn::parse_quote!(where A: From<B>)),
                methods: vec![replace!(
                    method =>
                    .arg_types = vec![syn::parse_quote!(A)],
                    .arg_names = vec![i("__arg_0")],
                )],
            },
        );

        assert_err(
            Actor::parse(&syn::parse_quote! {
                impl Trait for Foo {}
            }),
            "`impl Trait` is not supported",
        );

        assert_ok(
            Actor::parse(&syn::parse_quote! {
                impl ::module::Foo {}
            }),
            replace!(
                actor =>
                .type_ = syn::parse_quote!(::module::Foo),
            ),
        );
        assert_ok(
            Actor::parse(&syn::parse_quote! {
                impl<A, B, C> ::module::Foo<Arc<Mutex<(A, B, C)>>> {}
            }),
            replace!(
                actor =>
                .type_ = syn::parse_quote!(::module::Foo<Arc<Mutex<(A, B, C)>>>),
                .generics = syn::parse_quote!(<A, B, C>),
                .not_exposed = syn::parse_quote!(<A, B, C>),
            ),
        );
        assert_err(
            Actor::parse(&syn::parse_quote! {
                impl &Foo {}
            }),
            "currently only types like `module::Actor<T>` are supported",
        );
        assert_err(
            Actor::parse(&syn::parse_quote! {
                // This is not valid Rust.  Should we test it?
                impl <Foo as Iterator>::Item {}
            }),
            "currently only types like `module::Actor<T>` are supported",
        );
        assert_err(
            Actor::parse(&syn::parse_quote! {
                // This is not valid Rust.  Should we test it?
                impl<T> Foo::<T>::Bar {}
            }),
            "currently only types like `module::Actor<T>` are supported",
        );

        assert_ok(
            Actor::parse(&syn::parse_quote! {
                impl<T> Foo<'static, T> where T: 'static {}
            }),
            replace!(
                actor =>
                .type_ = syn::parse_quote!(Foo<'static, T>),
                .generics = g(
                    syn::parse_quote!(<T>),
                    syn::parse_quote!(where T: 'static),
                ),
                .not_exposed = g(
                    syn::parse_quote!(<T>),
                    syn::parse_quote!(where T: 'static),
                ),
            ),
        );
        assert_err(
            Actor::parse(&syn::parse_quote! {
                impl<'a, 'b> Foo<'a, 'b> where 'b: 'a {}
            }),
            "actor should not have a non-static lifetime parameter",
        );
        assert_err(
            Actor::parse(&syn::parse_quote! {
                impl Foo<'_> {}
            }),
            "actor should not have a non-static lifetime parameter",
        );
    }

    #[test]
    fn test_partition() {
        fn test<F>(testdata: &Generics, f: F, t_expect: &Generics, f_expect: &Generics)
        where
            F: FnMut(&Ident) -> bool,
        {
            let (t_actual, f_actual) = partition(testdata, f);
            assert_eq!(&t_actual, t_expect);
            assert_eq!(&f_actual, f_expect);
        }

        let testdata = g(
            syn::parse_quote!(<A, B, C>),
            syn::parse_quote!(where A: From<B>),
        );

        test(
            &testdata,
            |param| param == "A",
            &syn::parse_quote!(<A>),
            &g(
                syn::parse_quote!(<B, C>),
                syn::parse_quote!(where A: From<B>),
            ),
        );
        test(
            &testdata,
            |param| param != "A",
            &syn::parse_quote!(<B, C>),
            &g(syn::parse_quote!(<A>), syn::parse_quote!(where A: From<B>)),
        );

        test(
            &testdata,
            |param| param == "B",
            &syn::parse_quote!(<B>),
            &g(
                syn::parse_quote!(<A, C>),
                syn::parse_quote!(where A: From<B>),
            ),
        );
        test(
            &testdata,
            |param| param != "B",
            &syn::parse_quote!(<A, C>),
            &g(syn::parse_quote!(<B>), syn::parse_quote!(where A: From<B>)),
        );

        test(
            &testdata,
            |param| param == "A" || param == "B",
            &g(
                syn::parse_quote!(<A, B>),
                syn::parse_quote!(where A: From<B>),
            ),
            &syn::parse_quote!(<C>),
        );
        test(
            &testdata,
            |param| param != "A" && param != "B",
            &syn::parse_quote!(<C>),
            &g(
                syn::parse_quote!(<A, B>),
                syn::parse_quote!(where A: From<B>),
            ),
        );
    }

    #[test]
    fn actor_clear_annotations() {
        let mut input = syn::parse_quote! {
            impl Struct {
                #[foo]
                async fn f() {}

                #[bar]
                #[::g1_actor::actor::method()]
                #[g1_actor::actor::method()]
                #[actor::method()]
                #[method()]
                #[::actor::method()] // Not matched.
                fn g() {}
            }
        };
        Actor::clear_annotations(&mut input);
        assert_eq!(
            input,
            syn::parse_quote! {
                impl Struct {
                    #[foo]
                    async fn f() {}

                    #[bar]
                    #[::actor::method()]
                    fn g() {}
                }
            },
        );
    }

    #[test]
    fn method_try_parse() {
        assert_ok(
            Method::try_parse(&syn::parse_quote! {
                fn f() {}
            }),
            None,
        );

        let method = Method {
            visibility: None,
            asyncness: false,
            name: i("f"),
            has_receiver: false,
            arg_types: vec![],
            arg_names: vec![],
            ret_type: syn::parse_quote!(()),
            ret_expr: None,
        };
        assert_ok(
            Method::try_parse(&syn::parse_quote! {
                #[::g1_actor::actor::method()]
                fn f() {}
            }),
            Some(method.clone()),
        );

        assert_ok(
            Method::try_parse(&syn::parse_quote! {
                #[g1_actor::actor::method(pub)]
                async fn f(&self, _: String) -> usize {}
            }),
            Some(replace!(
                method =>
                .visibility = Some(syn::parse_quote!(pub)),
                .asyncness = true,
                .has_receiver = true,
                .arg_types = vec![syn::parse_quote!(String)],
                .arg_names = vec![i("__arg_0")],
                .ret_type = syn::parse_quote!(usize),
            )),
        );

        assert_ok(
            Method::try_parse(&syn::parse_quote! {
                #[actor::method(pub(crate), return { let x: C = x?; })]
                fn f(&mut self, x: A, y: B) -> Result<C, Error> {}
            }),
            Some(replace!(
                method =>
                .visibility = Some(syn::parse_quote!(pub(crate))),
                .has_receiver = true,
                .arg_types = vec![syn::parse_quote!(A), syn::parse_quote!(B)],
                .arg_names = vec![i("__arg_0"), i("__arg_1")],
                .ret_type = syn::parse_quote!(C),
                .ret_expr = Some((i("x"), syn::parse_quote!(x?))),
            )),
        );

        assert_err(
            Method::try_parse(&syn::parse_quote! {
                #[method]
                fn f() {}
            }),
            "expected attribute arguments in parentheses: #[method(...)]",
        );

        assert_err(
            Method::try_parse(&syn::parse_quote! {
                #[method(pub, pub)]
                fn f() {}
            }),
            "duplicated argument",
        );
        assert_err(
            Method::try_parse(&syn::parse_quote! {
                #[method(return { let x: T = x; })]
                #[method(return { let x: T = x; })]
                fn f() {}
            }),
            "duplicated argument",
        );

        assert_err(
            Method::try_parse(&syn::parse_quote! {
                #[method(skip)]
                fn f() {}
            }),
            "unknown argument",
        );

        assert_err(
            Method::try_parse(&syn::parse_quote! {
                #[method()]
                fn f<T>() {}
            }),
            "generic method is not supported",
        );

        assert_err(
            Method::try_parse(&syn::parse_quote! {
                #[method()]
                fn f(_: u8, ...) {}
            }),
            "variadic method is not supported",
        );

        assert_ok(
            Method::try_parse(&syn::parse_quote! {
                #[method()]
                fn f(self: &Self) {}
            }),
            Some(replace!(method => .has_receiver = true)),
        );
        assert_ok(
            Method::try_parse(&syn::parse_quote! {
                #[method()]
                fn f(self: &mut Box<Self>) {}
            }),
            Some(replace!(method => .has_receiver = true)),
        );
        assert_err(
            Method::try_parse(&syn::parse_quote! {
                #[method()]
                fn f(self) {}
            }),
            "currently only `&self` and `&mut self` are supported",
        );
        assert_err(
            Method::try_parse(&syn::parse_quote! {
                #[method()]
                fn f(self: Box<Self>) {}
            }),
            "currently only `&self` and `&mut self` are supported",
        );
    }

    #[test]
    fn method_signature_find() {
        fn test(testdata: &[ImplItem]) {
            let t = i("T");
            let u = i("U");
            for input in testdata {
                let method = Method::try_parse(input).unwrap().unwrap();
                assert!(
                    method.signature_find(&t),
                    "expect T in {}",
                    quote::quote!(#input),
                );
                assert!(
                    !method.signature_find(&u),
                    "expect U not in {}",
                    quote::quote!(#input),
                );
            }
        }

        test(&[
            syn::parse_quote! {
                #[method()]
                fn f(_: T) {}
            },
            syn::parse_quote! {
                #[method()]
                fn f(_: u8, _: T) {}
            },
            syn::parse_quote! {
                #[method()]
                fn f() -> T {}
            },
        ])
    }

    #[test]
    fn method_clear_annotations() {
        let mut input = syn::parse_quote! {
            #[method()]
            #[foo]
            #[actor::method()]
            #[bar]
            #[g1_actor::actor::method()]
            #[::g1_actor::actor::method()]
            #[::actor::method()] // Not matched.
            fn f() {}
        };
        Method::clear_annotations(&mut input);
        assert_eq!(
            input,
            syn::parse_quote! {
                #[foo]
                #[bar]
                #[::actor::method()]
                fn f() {}
            },
        );
    }

    #[test]
    fn test_parse_ret_expr() {
        const ERR: &str = "expect `{ let <ident>: <type> = <expr>; }`";

        assert_ok(
            parse_ret_expr(syn::parse_quote!({
                let x: T = Self::f();
            })),
            (syn::parse_quote!(T), (i("x"), syn::parse_quote!(Self::f()))),
        );

        assert_err(parse_ret_expr(syn::parse_quote!(1 + 1)), ERR);

        assert_err(parse_ret_expr(syn::parse_quote!({})), ERR);
        assert_err(
            parse_ret_expr(syn::parse_quote!({
                let x: T = Self::f();
                1 + 1
            })),
            ERR,
        );

        assert_err(parse_ret_expr(syn::parse_quote!({ 1 + 1 })), ERR);

        assert_err(
            parse_ret_expr(syn::parse_quote!({
                let x = y;
            })),
            ERR,
        );

        assert_err(
            parse_ret_expr(syn::parse_quote!({
                let Some(x): T = y;
            })),
            ERR,
        );
        assert_err(
            parse_ret_expr(syn::parse_quote!({
                let ref x: T = y;
            })),
            ERR,
        );
        assert_err(
            parse_ret_expr(syn::parse_quote!({
                let mut x: T = y;
            })),
            ERR,
        );
        assert_err(
            parse_ret_expr(syn::parse_quote!({
                let x @ Some(_): T = y;
            })),
            ERR,
        );
    }
}
