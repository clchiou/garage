use syn::parse::{Parse, ParseStream};
use syn::spanned::Spanned;
use syn::{
    Block, Error, Expr, ExprBlock, FieldsNamed, Ident, Local, LocalInit, Pat, Stmt, Token, Type,
    Visibility,
};

use crate::actor::{ActorArgs, AssocFunc, Fields, Loop, Message, Stub};
use crate::arg::{Arg, ArgValue, Args};
use crate::arg_parse::{
    ArgUnwrap, func_arg, named_scalar_arg, named_vec_arg, parse_args, scalar_arg,
};
use crate::error::ensure;

impl Parse for ActorArgs {
    fn parse(input: ParseStream) -> Result<Self, Error> {
        let args = input.parse_terminated(Arg::parse, Token![,])?;
        Ok(parse_args!(
            Self {
                stub,
                message,
                loop_,
            } = args
        ))
    }
}

func_arg!(stub: Stub);

impl TryFrom<Args> for Stub {
    type Error = Error;

    fn try_from(args: Args) -> Result<Self, Self::Error> {
        Ok(parse_args!(
            Self {
                skip,
                visibility,
                name,
                derive,
                fields,
                spawn,
                new,
            } = args
        ))
    }
}

func_arg!(message: Message);

impl TryFrom<Args> for Message {
    type Error = Error;

    fn try_from(args: Args) -> Result<Self, Self::Error> {
        Ok(parse_args!(
            Self {
                skip,
                visibility,
                name,
            } = args
        ))
    }
}

func_arg!(loop_: Loop);

impl TryFrom<Args> for Loop {
    type Error = Error;

    fn try_from(args: Args) -> Result<Self, Self::Error> {
        Ok(parse_args!(
            Self {
                skip,
                visibility,
                name,
                new,
                run,
                reacts,
                ret_type,
                ret_value,
            } = args
        ))
    }
}

func_arg!(spawn: AssocFunc);
func_arg!(new: AssocFunc);
func_arg!(run: AssocFunc);

impl TryFrom<Args> for AssocFunc {
    type Error = Error;

    fn try_from(args: Args) -> Result<Self, Self::Error> {
        Ok(parse_args!(
            Self {
                skip,
                visibility,
                name,
            } = args
        ))
    }
}

named_scalar_arg!(skip: () = Arg::NameOnly(_) => ());

impl ArgUnwrap<()> for bool {
    fn unwrap(argv: Option<()>) -> Self {
        argv.is_some()
    }
}

scalar_arg! {
    pub(super) visibility: Visibility =
    Arg::ValueOnly(ArgValue::Visibility(visibility)) => (visibility.span(), visibility),
}

scalar_arg! {
    name: Ident =
    Arg::NameOnly(name) if name != "skip" => (name.span(), name),
    // In case the user genuinely wants to name something "skip".
    arg if arg.name().is_some_and(|arg_name| arg_name == "name") => (
        arg.name().unwrap().span(),
        match arg {
            Arg::NameValue(_, ArgValue::Ident(name)) => name,
            _ => return Err(Error::new(arg.name().unwrap().span(), "invalid argument value")),
        },
    ),
}

func_arg!(derive: Derive);

struct Derive(Vec<Ident>);

impl TryFrom<Args> for Derive {
    type Error = Error;

    fn try_from(args: Args) -> Result<Self, Self::Error> {
        Ok(Self(
            args.into_iter()
                .map(|trait_| match trait_ {
                    Arg::NameOnly(trait_) => Ok(trait_),
                    arg => Err(Error::new(arg.span(), "expect `Trait`")),
                })
                .try_collect()?,
        ))
    }
}

impl ArgUnwrap<Derive> for Option<Vec<Ident>> {
    fn unwrap(argv: Option<Derive>) -> Self {
        argv.map(|Derive(derive)| derive)
    }
}

scalar_arg! {
    fields: Fields =
    Arg::ValueOnly(ArgValue::Struct(token, fields)) => (token.span(), parse_fields(fields)?),
}

fn parse_fields(fields: FieldsNamed) -> Result<Fields, Error> {
    let mut fields = fields.named;
    for field in &fields {
        let name = field.ident.as_ref().expect("field name");
        ensure!(
            !name.to_string().starts_with("__"),
            name.span(),
            "forbidden field name",
        );
    }
    // It is convenient to always include a trailing comma.
    if !fields.empty_or_trailing() {
        fields.push_punct(Default::default());
    }
    Ok(fields)
}

named_vec_arg!(reacts = react: (Pat, Expr, Expr));

named_scalar_arg! {
    pub(super) react: (Pat, Expr, Expr) =
    Arg::NameValue(_, ArgValue::Expr(block)) => parse_react(block)?,
}

fn parse_react(mut block: Expr) -> Result<(Pat, Expr, Expr), Error> {
    let span = block.span();
    let error = || Error::new(span, "expect `{ let <pat> = <expr>; ... }`");

    let Expr::Block(ExprBlock {
        block: Block { stmts, .. },
        ..
    }) = &mut block
    else {
        return Err(error());
    };

    if stmts.is_empty() {
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

    Ok((pat, Box::into_inner(expr), block))
}

scalar_arg! {
    pub(super) ret_type: Type =
    Arg::ValueOnly(ArgValue::Type(token, ret_type)) => (token.span(), ret_type),
}

scalar_arg! {
    pub(super) ret_value: Expr =
    Arg::ValueOnly(ArgValue::Return(token, ret_value)) => (token.span(), ret_value),
}

#[cfg(test)]
mod tests {
    use crate::testing::{assert_err, assert_ok, i, ps, replace};

    use super::*;

    #[test]
    fn actor_args() {
        assert_ok(syn::parse2(quote::quote!()), ActorArgs::default());
        assert_ok(
            syn::parse2(quote::quote!(stub(), message(), loop_())),
            ActorArgs::default(),
        );

        assert_err::<ActorArgs>(
            syn::parse2(quote::quote!(stub(), stub())),
            "duplicated argument",
        );
        assert_err::<ActorArgs>(
            syn::parse2(quote::quote!(message(), message())),
            "duplicated argument",
        );
        assert_err::<ActorArgs>(
            syn::parse2(quote::quote!(loop_(), loop_())),
            "duplicated argument",
        );

        assert_err::<ActorArgs>(syn::parse2(quote::quote!(stub)), "invalid argument value");

        assert_err::<ActorArgs>(syn::parse2(quote::quote!(skip)), "unknown argument");
        assert_err::<ActorArgs>(syn::parse2(quote::quote!({})), "unknown argument");
    }

    #[test]
    fn stub() {
        fn parse(args: Args) -> Result<Stub, Error> {
            args.try_into()
        }

        assert_ok(parse(syn::parse_quote!()), Stub::default());

        assert_err(
            parse(syn::parse_quote!(
                react = {
                    let x = x;
                }
            )),
            "unknown argument",
        );
        assert_err(parse(syn::parse_quote!(type ())), "unknown argument");
        assert_err(parse(syn::parse_quote!(return ())), "unknown argument");
    }

    #[test]
    fn message() {
        fn parse(args: Args) -> Result<Message, Error> {
            args.try_into()
        }

        assert_ok(parse(syn::parse_quote!()), Message::default());

        assert_err(parse(syn::parse_quote!(struct {})), "unknown argument");
        assert_err(
            parse(syn::parse_quote!(
                react = {
                    let x = x;
                }
            )),
            "unknown argument",
        );
        assert_err(parse(syn::parse_quote!(type ())), "unknown argument");
        assert_err(parse(syn::parse_quote!(return ())), "unknown argument");
    }

    #[test]
    fn loop_() {
        fn parse(args: Args) -> Result<Loop, Error> {
            args.try_into()
        }

        assert_ok(parse(syn::parse_quote!()), Loop::default());

        assert_err(parse(syn::parse_quote!(struct {})), "unknown argument");
    }

    #[test]
    fn assoc_func() {
        fn parse(args: Args) -> Result<AssocFunc, Error> {
            args.try_into()
        }

        assert_ok(parse(syn::parse_quote!()), AssocFunc::default());
        assert_ok(
            parse(syn::parse_quote!(skip, pub, Foo)),
            AssocFunc {
                skip: true,
                visibility: Some(syn::parse_quote!(pub)),
                name: Some(i("Foo")),
            },
        );
        assert_ok(
            parse(syn::parse_quote!(name = skip)),
            AssocFunc {
                name: Some(i("skip")),
                ..Default::default()
            },
        );

        assert_err(parse(syn::parse_quote!(struct {})), "unknown argument");
    }

    #[test]
    fn test_arg() {
        #[derive(Clone, Debug, Default, PartialEq)]
        struct TestArg {
            skip: bool,

            visibility: Option<Visibility>,

            name: Option<Ident>,
            derive: Option<Vec<Ident>>,

            fields: Fields,

            reacts: Vec<(Pat, Expr, Expr)>,

            ret_type: Option<Type>,
            ret_value: Option<Expr>,
        }

        impl TryFrom<Args> for TestArg {
            type Error = Error;

            fn try_from(args: Args) -> Result<Self, Self::Error> {
                Ok(parse_args!(
                    Self {
                        skip,
                        visibility,
                        name,
                        derive,
                        fields,
                        reacts,
                        ret_type,
                        ret_value,
                    } = args
                ))
            }
        }

        fn parse(args: Args) -> Result<TestArg, Error> {
            args.try_into()
        }

        let test_arg = TestArg::default();
        assert_ok(parse(syn::parse_quote!()), test_arg.clone());

        assert_ok(
            parse(syn::parse_quote!(
                skip,
                pub,
                Foo,
                derive(Clone, Debug),
                struct {},
                react = { let x = x; },
                type Result<(), Error>,
                return Ok(()),
            )),
            TestArg {
                skip: true,
                visibility: Some(syn::parse_quote!(pub)),
                name: Some(i("Foo")),
                derive: Some(vec![i("Clone"), i("Debug")]),
                fields: ps([]),
                reacts: vec![(
                    syn::parse_quote!(x),
                    syn::parse_quote!(x),
                    syn::parse_quote!({}),
                )],
                ret_type: Some(syn::parse_quote!(Result<(), Error>)),
                ret_value: Some(syn::parse_quote!(Ok(()))),
            },
        );
        assert_ok(
            parse(syn::parse_quote!(
                name = skip,
                struct { _x: u8, y: String },
                react = { let Some(x) = Self::f(); x? },
                react = { let x = g(); let x = self.f(x); x?; },
            )),
            replace!(
                test_arg =>
                .name = Some(i("skip")),
                .fields = ps([
                    syn::parse_quote!(_x: u8),
                    syn::parse_quote!(y: String),
                ]),
                .reacts = vec![
                    (
                        syn::parse_quote!(Some(x)),
                        syn::parse_quote!(Self::f()),
                        syn::parse_quote!({ x? }),
                    ),
                    (
                        syn::parse_quote!(x),
                        syn::parse_quote!(g()),
                        syn::parse_quote!({ let x = self.f(x); x?; }),
                    ),
                ],
            ),
        );

        for result in [
            parse(syn::parse_quote!(skip, skip)),
            parse(syn::parse_quote!(pub, pub(crate))),
            parse(syn::parse_quote!(Foo, Bar)),
            parse(syn::parse_quote!(Foo, name = Bar)),
            parse(syn::parse_quote!(derive(), derive())),
            parse(syn::parse_quote!(struct {}, struct {})),
            parse(syn::parse_quote!(type u8, type String)),
            parse(syn::parse_quote!(return 1, return 2)),
        ] {
            assert_err(result, "duplicated argument");
        }

        assert_err(parse(syn::parse_quote!(skip())), "invalid argument value");

        assert_err(parse(syn::parse_quote!(name())), "invalid argument value");

        assert_err(
            parse(syn::parse_quote!(derive = Debug)),
            "invalid argument value",
        );
        assert_err(parse(syn::parse_quote!(derive(p = q))), "expect `Trait`");

        assert_err(parse(syn::parse_quote!(react())), "invalid argument value");

        assert_err(parse(syn::parse_quote!(spam = egg)), "unknown argument");
        assert_err(parse(syn::parse_quote!(f())), "unknown argument");
        assert_err(parse(syn::parse_quote!({ 1 + 2 })), "unknown argument");
    }

    #[test]
    fn test_parse_fields() {
        assert_ok(parse_fields(syn::parse_quote!({})), ps([]));

        assert_ok(
            parse_fields(syn::parse_quote!({ x: u8 })),
            ps([syn::parse_quote!(x: u8)]),
        );
        assert_ok(
            parse_fields(syn::parse_quote!({ x: u8, })),
            ps([syn::parse_quote!(x: u8)]),
        );

        assert_ok(
            parse_fields(syn::parse_quote!({ x: u8, y: u16 })),
            ps([syn::parse_quote!(x: u8), syn::parse_quote!(y: u16)]),
        );
        assert_ok(
            parse_fields(syn::parse_quote!({ x: u8, y: u16, })),
            ps([syn::parse_quote!(x: u8), syn::parse_quote!(y: u16)]),
        );

        assert_err(
            parse_fields(syn::parse_quote!({ __x: u8 })),
            "forbidden field name",
        );
    }

    #[test]
    fn test_parse_react() {
        const ERR: &str = "expect `{ let <pat> = <expr>; ... }`";

        assert_ok(
            parse_react(syn::parse_quote!({
                let x = Self::f();
            })),
            (
                syn::parse_quote!(x),
                syn::parse_quote!(Self::f()),
                syn::parse_quote!({}),
            ),
        );
        assert_ok(
            parse_react(syn::parse_quote!({
                let Some(x) = Self::f();
                x?
            })),
            (
                syn::parse_quote!(Some(x)),
                syn::parse_quote!(Self::f()),
                syn::parse_quote!({ x? }),
            ),
        );

        assert_err(parse_react(syn::parse_quote!(1 + 1)), ERR);

        assert_err(parse_react(syn::parse_quote!({})), ERR);

        assert_err(
            parse_react(syn::parse_quote!({
                x = 1;
            })),
            ERR,
        );
    }
}
