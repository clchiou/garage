use proc_macro2::Span;
use syn::parse::{End, Parse, ParseStream};
use syn::punctuated::Punctuated;
use syn::spanned::Spanned;
use syn::token::{Brace, Paren};
use syn::{Error, Expr, FieldsNamed, Ident, Token, Type, Visibility};

//
// We report the error at the span of the first token, which appears to be sufficiently
// informative, rather than using the span of the entire `Arg`.
//

#[cfg_attr(test, derive(Debug, PartialEq))]
pub(crate) enum Arg {
    NameOnly(Ident),
    ValueOnly(ArgValue),
    NameValue(Ident, ArgValue),
    Call(Ident, Args),
}

pub(crate) type Args = Punctuated<Arg, Token![,]>;

#[cfg_attr(test, derive(Debug, PartialEq))]
pub(crate) enum ArgValue {
    Expr(Expr),
    Ident(Ident),
    Return(Token![return], Expr),
    Struct(Token![struct], FieldsNamed),
    Type(Token![type], Type),
    Visibility(Visibility),
}

impl Parse for Arg {
    fn parse(input: ParseStream) -> Result<Self, Error> {
        if !input.peek(Ident) {
            Ok(Self::ValueOnly(input.parse()?))
        } else if input.peek2(Token![,]) || input.peek2(End) {
            Ok(Self::NameOnly(input.parse()?))
        } else if input.peek2(Token![=]) {
            let name = input.parse()?;
            let _ = input.parse::<Token![=]>()?;
            Ok(Self::NameValue(name, input.parse()?))
        } else if input.peek2(Paren) {
            let name = input.parse()?;
            let args;
            let _: Paren = syn::parenthesized!(args in input);
            Ok(Self::Call(
                name,
                args.parse_terminated(Arg::parse, Token![,])?,
            ))
        } else {
            Err(input.error("incorrect argument syntax"))
        }
    }
}

impl Parse for ArgValue {
    fn parse(input: ParseStream) -> Result<Self, Error> {
        if input.peek(Ident) {
            Ok(Self::Ident(input.parse()?))
        } else if input.peek(Brace) {
            Ok(Self::Expr(input.parse()?))
        } else if input.peek(Token![return]) {
            Ok(Self::Return(input.parse()?, input.parse()?))
        } else if input.peek(Token![struct]) {
            Ok(Self::Struct(input.parse()?, input.parse()?))
        } else if input.peek(Token![type]) {
            Ok(Self::Type(input.parse()?, input.parse()?))
        } else if input.peek(Token![pub]) {
            Ok(Self::Visibility(input.parse()?))
        } else {
            Err(input.error("incorrect argument value syntax"))
        }
    }
}

impl Arg {
    pub(crate) fn name(&self) -> Option<&Ident> {
        match self {
            Self::NameOnly(name) | Self::NameValue(name, _) | Self::Call(name, _) => Some(name),
            Self::ValueOnly(_) => None,
        }
    }

    pub(crate) fn span(&self) -> Span {
        match self {
            Self::NameOnly(name) | Self::NameValue(name, _) | Self::Call(name, _) => name.span(),
            Self::ValueOnly(value) => value.span(),
        }
    }
}

impl ArgValue {
    pub(crate) fn span(&self) -> Span {
        match self {
            Self::Expr(expr) => expr.span(),
            Self::Ident(ident) => ident.span(),
            Self::Return(token, _) => token.span(),
            Self::Struct(token, _) => token.span(),
            Self::Type(token, _) => token.span(),
            Self::Visibility(visibility) => visibility.span(),
        }
    }
}

#[cfg(test)]
mod tests {
    use syn::punctuated::Pair;

    use crate::testing::{assert_err, assert_ok, i, ir};

    use super::*;

    #[test]
    fn arg() {
        assert_ok(syn::parse2(quote::quote!(foo)), Arg::NameOnly(i("foo")));
        assert_ok(syn::parse2(quote::quote!(r#pub)), Arg::NameOnly(ir("pub")));

        assert_ok(
            syn::parse2(quote::quote!(pub)),
            Arg::ValueOnly(ArgValue::Visibility(Visibility::Public(Default::default()))),
        );

        assert_ok(
            syn::parse2(quote::quote!(foo = bar)),
            Arg::NameValue(i("foo"), ArgValue::Ident(i("bar"))),
        );

        assert_ok(
            syn::parse2(quote::quote!(foo())),
            Arg::Call(i("foo"), Punctuated::new()),
        );
        assert_ok(
            syn::parse2(quote::quote!(foo(bar))),
            Arg::Call(i("foo"), [Arg::NameOnly(i("bar"))].into_iter().collect()),
        );
        assert_ok(
            syn::parse2(quote::quote!(foo(x = y, spam(egg /* Trailing comma. */,)))),
            Arg::Call(
                i("foo"),
                [
                    Arg::NameValue(i("x"), ArgValue::Ident(i("y"))),
                    Arg::Call(
                        i("spam"),
                        [Pair::Punctuated(
                            Arg::NameOnly(i("egg")),
                            Default::default(),
                        )]
                        .into_iter()
                        .collect(),
                    ),
                ]
                .into_iter()
                .collect(),
            ),
        );

        assert_err::<Arg>(syn::parse2(quote::quote!(x.y)), "incorrect argument syntax");
    }

    #[test]
    fn arg_value() {
        assert_ok(syn::parse2(quote::quote!(foo)), ArgValue::Ident(i("foo")));
        assert_ok(
            syn::parse2(quote::quote!(r#pub)),
            ArgValue::Ident(ir("pub")),
        );

        assert_ok(
            syn::parse2(quote::quote!({
                1 + 2;
                3
            })),
            ArgValue::Expr(syn::parse_quote!({
                1 + 2;
                3
            })),
        );
        assert_ok(
            syn::parse2(quote::quote!(return 1 + 2)),
            ArgValue::Return(Default::default(), syn::parse_quote!(1 + 2)),
        );

        assert_ok(
            syn::parse2(quote::quote!(struct {})),
            ArgValue::Struct(Default::default(), syn::parse_quote!({})),
        );
        assert_ok(
            syn::parse2(quote::quote!(struct { x: u8 })),
            ArgValue::Struct(Default::default(), syn::parse_quote!({ x: u8 })),
        );

        assert_ok(
            syn::parse2(quote::quote!(type Result<(), Error>)),
            ArgValue::Type(Default::default(), syn::parse_quote!(Result<(), Error>)),
        );

        assert_ok(
            syn::parse2(quote::quote!(pub)),
            ArgValue::Visibility(Visibility::Public(Default::default())),
        );

        assert_err::<ArgValue>(
            syn::parse2(quote::quote!(1 + 2)),
            "incorrect argument value syntax",
        );
    }
}
