use std::borrow::Cow;
use std::fmt;

use proc_macro2::TokenStream;
use syn::parse::{Parse, ParseStream};
use syn::punctuated::Punctuated;
use syn::spanned::Spanned;
use syn::{
    Attribute, Data, DataEnum, DataStruct, DeriveInput, Error, Field, Ident, LitStr, Path, QSelf,
    Token, Type, TypeGroup, TypeParen, TypePath,
};

macro_rules! ensure {
    ($predicate:expr, $span:expr, $message:expr $(,)?) => {
        if !$predicate {
            return Err(Error::new($span, $message));
        }
    };
}

//
// `DeriveInput`
//

pub(crate) fn optional(mut input: DeriveInput) -> Result<TokenStream, Error> {
    match &mut input.data {
        Data::Struct(DataStruct { fields, .. }) => {
            for field in fields {
                optional_loop_body(field)?;
            }
        }
        Data::Enum(DataEnum { variants, .. }) => {
            for variant in variants {
                for field in &mut variant.fields {
                    optional_loop_body(field)?;
                }
            }
        }
        Data::Union(union) => {
            return Err(Error::new(
                union.union_token.span,
                "`optional` does not support union",
            ));
        }
    }
    Ok(quote::quote!(#input))
}

fn optional_loop_body(field: &mut Field) -> Result<(), Error> {
    if is_option(&field.ty) {
        annotate_field(field)
    } else {
        for attr in &field.attrs {
            ensure!(
                Attr::try_parse(attr)?.is_none(),
                field.ty.span(),
                "`optional(...)` may only be applied to fields of type `Option<T>`",
            );
        }
        Ok(())
    }
}

/// Matches a type that is equivalent to `Option<T>`.
fn is_option(type_: &Type) -> bool {
    match type_ {
        Type::Group(TypeGroup { elem, .. }) | Type::Paren(TypeParen { elem, .. }) => {
            is_option(elem)
        }
        Type::Path(TypePath { qself, path }) => match qself {
            Some(QSelf { ty, .. }) => is_option(ty),
            None => {
                match_path(path, &["std", "option", "Option"])
                    || match_path(path, &["core", "option", "Option"])
            }
        },
        _ => false,
    }
}

fn annotate_field(field: &mut Field) -> Result<(), Error> {
    let mut skip = false;
    let mut with = None;
    let mut conflict = None;

    let mut i = 0;
    while i < field.attrs.len() {
        match Attr::try_parse(&field.attrs[i])? {
            Some(Attr(args)) => {
                for arg in args {
                    match arg {
                        AttrArg::Skip(ident) => {
                            ensure!(!skip, ident.span(), "duplicated `optional(skip)`");
                            skip = true;
                        }
                        AttrArg::With(ident, path) => {
                            ensure!(
                                with.is_none(),
                                ident.span(),
                                "duplicated `optional(with = \"...\")`",
                            );
                            with = Some(path);
                        }
                    }
                    ensure!(
                        !(skip && with.is_some()),
                        field.attrs[i].span(),
                        "both `optional(skip)` and `optional(with = \"...\")` are set",
                    );
                }
                field.attrs.remove(i);
            }
            None => {
                if let Err(error) = ensure_no_conflict(&field.attrs[i]) {
                    conflict.get_or_insert(error); // Keep the first conflict.
                }
                i += 1;
            }
        }
    }

    if skip {
        return Ok(());
    }

    if let Some(error) = conflict {
        return Err(error);
    }

    let serde_with = match with {
        Some(path) => Cow::Owned(format!("::bt_serde::private::Optional::<{path}>")),
        None => Cow::Borrowed("::bt_serde::private::optional"),
    };
    field.attrs.push(syn::parse_quote!(#[serde(
        default,
        skip_serializing_if = "::std::option::Option::is_none",
        with = #serde_with
    )]));

    Ok(())
}

//
// `Attr`
//

#[cfg_attr(test, derive(Debug, PartialEq))]
struct Attr(AttrArgs);

impl Attr {
    fn try_parse(attr: &Attribute) -> Result<Option<Self>, Error> {
        Ok(if match_path(attr.path(), &["bt_serde", "optional"]) {
            Some(Self(attr.parse_args_with(AttrArgs::parse_terminated)?))
        } else {
            None
        })
    }
}

type AttrArgs = Punctuated<AttrArg, Token![,]>;

#[cfg_attr(test, derive(Debug, PartialEq))]
enum AttrArg {
    Skip(Ident),
    With(Ident, String),
}

impl Parse for AttrArg {
    fn parse(input: ParseStream) -> Result<Self, Error> {
        let name = input.parse::<Ident>()?;
        if name == "skip" {
            Ok(Self::Skip(name))
        } else if name == "with" {
            input.parse::<Token![=]>()?;
            Ok(Self::With(name, input.parse::<LitStr>()?.value()))
        } else {
            Err(Error::new(name.span(), "unknown `optional(...)` argument"))
        }
    }
}

//
// `SerdeAttrArg`
//

fn ensure_no_conflict(attr: &Attribute) -> Result<(), Error> {
    if attr.path().is_ident("serde") {
        for arg in attr.parse_args_with(SerdeAttrArgs::parse_terminated)? {
            arg.ensure_no_conflict()?;
        }
    }
    Ok(())
}

type SerdeAttrArgs = Punctuated<SerdeAttrArg, Token![,]>;

#[cfg_attr(test, derive(Debug, PartialEq))]
struct SerdeAttrArg {
    name: Ident,
    // In our use case, the argument value is ignored.
}

impl Parse for SerdeAttrArg {
    fn parse(input: ParseStream) -> Result<Self, Error> {
        let name = input.parse()?;
        if input.peek(Token![=]) {
            input.parse::<Token![=]>()?;
            input.parse::<LitStr>()?;
        }
        Ok(Self { name })
    }
}

impl SerdeAttrArg {
    fn ensure_no_conflict(&self) -> Result<(), Error> {
        // At the moment, we do not reconcile Serde attributes applied by you with those applied by
        // us; instead, we simply return an error.
        const RESERVED: &[&str] = &["default", "skip_serializing_if", "with"];
        ensure!(
            RESERVED.iter().all(|reserved| self.name != reserved),
            self.name.span(),
            fmt::from_fn(|f| { write!(f, "`optional(...)` conflict with `serde({})`", self.name) }),
        );
        Ok(())
    }
}

//
// Helpers.
//

fn match_path(path: &Path, expect: &[&str]) -> bool {
    // `path` should not contain angle brackets, except for the last segment.
    if !path
        .segments
        .iter()
        .rev()
        .skip(1)
        .all(|segment| segment.arguments.is_none())
    {
        return false;
    }

    fn segments(path: &Path) -> impl Iterator<Item = &Ident> {
        path.segments.iter().map(|segment| &segment.ident)
    }

    (path.leading_colon.is_none() && segments(path).eq([expect.last().expect("non-empty")]))
        || segments(path).eq(expect)
}

#[cfg(test)]
mod tests {
    use proc_macro2::Span;

    use super::*;

    fn ident(name: &str) -> Ident {
        Ident::new(name, Span::call_site())
    }

    fn assert_ok<T>(result: Result<T, Error>, expect: T)
    where
        T: fmt::Debug + PartialEq,
    {
        assert_eq!(result.unwrap(), expect);
    }

    fn assert_err<T>(result: Result<T, Error>, error: &str)
    where
        T: fmt::Debug,
    {
        assert_eq!(result.unwrap_err().to_string(), error);
    }

    #[test]
    fn test_optional() {
        fn test_ok(input: DeriveInput, expect: TokenStream) {
            assert_eq!(optional(input).unwrap().to_string(), expect.to_string());
        }

        test_ok(
            syn::parse_quote!(
                struct Struct {
                    a: Option<A>,

                    #[optional(skip)]
                    #[serde(with = "Spam")]
                    b: std::option::Option<B>,

                    #[optional(with = "Egg")]
                    #[serde(rename = "c2")]
                    c: ::core::option::Option<C>,

                    d: D,
                }
            ),
            quote::quote!(
                struct Struct {
                    #[serde(
                        default,
                        skip_serializing_if = "::std::option::Option::is_none",
                        with = "::bt_serde::private::optional"
                    )]
                    a: Option<A>,

                    #[serde(with = "Spam")]
                    b: std::option::Option<B>,

                    #[serde(rename = "c2")]
                    #[serde(
                        default,
                        skip_serializing_if = "::std::option::Option::is_none",
                        with = "::bt_serde::private::Optional::<Egg>"
                    )]
                    c: ::core::option::Option<C>,

                    d: D,
                }
            ),
        );

        test_ok(
            syn::parse_quote!(
                struct Tuple(
                    Option<A>,
                    #[optional(skip)]
                    #[serde(with = "Spam")]
                    std::option::Option<B>,
                    #[optional(with = "Egg")]
                    #[foo]
                    ::core::option::Option<C>,
                    D,
                );
            ),
            quote::quote!(
                struct Tuple(
                    #[serde(
                        default,
                        skip_serializing_if = "::std::option::Option::is_none",
                        with = "::bt_serde::private::optional"
                    )]
                    Option<A>,
                    #[serde(with = "Spam")] std::option::Option<B>,
                    #[foo]
                    #[serde(
                        default,
                        skip_serializing_if = "::std::option::Option::is_none",
                        with = "::bt_serde::private::Optional::<Egg>"
                    )]
                    ::core::option::Option<C>,
                    D,
                );
            ),
        );

        #[rustfmt::skip]
        test_ok(
            syn::parse_quote!(
                enum Enum {
                    Unit,

                    #[foo]
                    Newtype(
                        #[bar]
                        Option<A>,
                    ),

                    Tuple(
                        #[optional(with = "Foo")]
                        std::option::Option<B>,
                        C,
                    ),

                    Struct {
                        #[optional(skip)]
                        d: ::core::option::Option<D>,
                        e: E,
                    },
                }
            ),
            quote::quote!(
                enum Enum {
                    Unit,

                    #[foo]
                    Newtype(
                        #[bar]
                        #[serde(
                            default,
                            skip_serializing_if = "::std::option::Option::is_none",
                            with = "::bt_serde::private::optional"
                        )]
                        Option<A>,
                    ),

                    Tuple(
                        #[serde(
                            default,
                            skip_serializing_if = "::std::option::Option::is_none",
                            with = "::bt_serde::private::Optional::<Foo>"
                        )]
                        std::option::Option<B>,
                        C,
                    ),

                    Struct {
                        d: ::core::option::Option<D>,
                        e: E,
                    },
                }
            ),
        );

        assert_err(
            optional(syn::parse_quote!(
                union Union {
                    x: T,
                }
            )),
            "`optional` does not support union",
        );
        assert_err(
            optional(syn::parse_quote!(
                struct Struct {
                    #[optional()]
                    x: T,
                }
            )),
            "`optional(...)` may only be applied to fields of type `Option<T>`",
        );
    }

    #[test]
    fn test_is_option() {
        fn test(type_: Type, expect: bool) {
            assert_eq!(is_option(&type_), expect);
        }

        test(syn::parse_quote!(Option), true);
        test(syn::parse_quote!(Option<()>), true);
        test(syn::parse_quote!(Option::<()>), true);

        test(syn::parse_quote!(std::option::Option), true);
        test(syn::parse_quote!(::std::option::Option), true);

        test(syn::parse_quote!(core::option::Option), true);
        test(syn::parse_quote!(::core::option::Option), true);

        test(syn::parse_quote!(std::option<T>::Option), false);
        test(syn::parse_quote!(std::option::<T>::Option), false);
        test(syn::parse_quote!(::Option), false);
        test(syn::parse_quote!(__private::Option), false);
        test(syn::parse_quote!(::__private::Option), false);
        test(syn::parse_quote!(StdOption), false);
    }

    #[test]
    fn test_annotate_field() {
        fn test_ok(mut field: Field, expect: Field) {
            assert_ok(annotate_field(&mut field), ());
            assert_eq!(field, expect);
        }

        fn test_err(mut field: Field, error: &str) {
            assert_err(annotate_field(&mut field), error);
        }

        test_ok(
            syn::parse_quote!(
                x: Option<T>
            ),
            syn::parse_quote!(
                #[serde(
                    default,
                    skip_serializing_if = "::std::option::Option::is_none",
                    with = "::bt_serde::private::optional"
                )]
                x: Option<T>
            ),
        );
        test_ok(
            syn::parse_quote!(
                #[foo]
                #[serde(rename = "y")]
                #[bar]
                x: Option<T>
            ),
            syn::parse_quote!(
                #[foo]
                #[serde(rename = "y")]
                #[bar]
                #[serde(
                    default,
                    skip_serializing_if = "::std::option::Option::is_none",
                    with = "::bt_serde::private::optional"
                )]
                x: Option<T>
            ),
        );

        test_ok(
            syn::parse_quote!(
                #[spam]
                #[optional(skip)]
                #[egg]
                x: Option<T>
            ),
            syn::parse_quote!(
                #[spam]
                #[egg]
                x: Option<T>
            ),
        );
        test_ok(
            syn::parse_quote!(
                #[serde(default)]
                #[optional(skip)]
                #[serde(skip_serializing_if = "...")]
                x: Option<T>
            ),
            syn::parse_quote!(
                #[serde(default)]
                #[serde(skip_serializing_if = "...")]
                x: Option<T>
            ),
        );

        test_ok(
            syn::parse_quote!(
                #[optional(with = "foo::Bar")]
                x: Option<T>
            ),
            syn::parse_quote!(
                #[serde(
                    default,
                    skip_serializing_if = "::std::option::Option::is_none",
                    with = "::bt_serde::private::Optional::<foo::Bar>"
                )]
                x: Option<T>
            ),
        );

        test_err(
            syn::parse_quote!(
                #[optional(skip)]
                #[optional(skip)]
                x: Option<T>
            ),
            "duplicated `optional(skip)`",
        );
        test_err(
            syn::parse_quote!(
                #[optional(with = "")]
                #[optional(with = "", skip)]
                x: Option<T>
            ),
            "duplicated `optional(with = \"...\")`",
        );
        test_err(
            syn::parse_quote!(
                #[serde(with = "")]
                #[serde(default)]
                x: Option<T>
            ),
            "`optional(...)` conflict with `serde(with)`",
        );
        test_err(
            syn::parse_quote!(
                #[optional(skip)]
                #[optional(with = "foo", skip)]
                x: Option<T>
            ),
            "both `optional(skip)` and `optional(with = \"...\")` are set",
        );
    }

    #[test]
    fn attr() {
        assert_ok(Attr::try_parse(&syn::parse_quote!(#[foo])), None);
        assert_ok(Attr::try_parse(&syn::parse_quote!(#[foo::bar])), None);

        assert_ok(
            Attr::try_parse(&syn::parse_quote!(#[optional()])),
            Some(Attr(AttrArgs::new())),
        );
        assert_ok(
            Attr::try_parse(&syn::parse_quote!(#[bt_serde::optional()])),
            Some(Attr(AttrArgs::new())),
        );
        assert_ok(
            Attr::try_parse(&syn::parse_quote!(#[::bt_serde::optional()])),
            Some(Attr(AttrArgs::new())),
        );

        assert_ok(
            Attr::try_parse(&syn::parse_quote!(#[optional(skip, with = "foobar", skip)])),
            Some(Attr(AttrArgs::from_iter([
                AttrArg::Skip(ident("skip")),
                AttrArg::With(ident("with"), "foobar".to_string()),
                AttrArg::Skip(ident("skip")),
            ]))),
        );

        assert_err(
            Attr::try_parse(&syn::parse_quote!(#[optional])),
            "expected attribute arguments in parentheses: #[optional(...)]",
        );
    }

    #[test]
    fn attr_arg() {
        assert_ok(
            syn::parse_str::<AttrArg>("skip"),
            AttrArg::Skip(ident("skip")),
        );
        assert_ok(
            syn::parse_str::<AttrArg>("with = \"foobar\""),
            AttrArg::With(ident("with"), "foobar".to_string()),
        );

        fn test_err(code: &str, error: &str) {
            assert_err(syn::parse_str::<AttrArg>(code), error);
        }

        test_err("skip = \"foobar\"", "unexpected token");
        test_err("with", "expected `=`");
        test_err(
            "with = ",
            "unexpected end of input, expected string literal",
        );
        test_err("foobar", "unknown `optional(...)` argument");
    }

    #[test]
    fn test_ensure_no_conflict() {
        fn test_ok(attr: Attribute) {
            assert_ok(ensure_no_conflict(&attr), ());
        }

        fn test_err(attr: Attribute, error: &str) {
            assert_err(ensure_no_conflict(&attr), error);
        }

        test_ok(syn::parse_quote!(#[foo]));
        test_ok(syn::parse_quote!(#[serde()]));
        test_ok(syn::parse_quote!(#[serde(foo)]));
        test_ok(syn::parse_quote!(#[serde(foo, bar, spam = "egg")]));

        test_err(
            syn::parse_quote!(#[serde]),
            "expected attribute arguments in parentheses: #[serde(...)]",
        );
        test_err(
            syn::parse_quote!(#[serde(foo, default)]),
            "`optional(...)` conflict with `serde(default)`",
        );
        test_err(
            syn::parse_quote!(#[serde(foo, skip_serializing_if = "Option::is_none")]),
            "`optional(...)` conflict with `serde(skip_serializing_if)`",
        );
        test_err(
            syn::parse_quote!(#[serde(foo, with = "...")]),
            "`optional(...)` conflict with `serde(with)`",
        );
    }

    #[test]
    fn serde_attr_arg() {
        assert_ok(
            syn::parse_str::<SerdeAttrArg>("foobar"),
            SerdeAttrArg {
                name: ident("foobar"),
            },
        );

        fn test_err(code: &str, error: &str) {
            assert_err(syn::parse_str::<SerdeAttrArg>(code), error);
        }

        test_err("1 + 1", "expected identifier");
        test_err(
            "default = ",
            "unexpected end of input, expected string literal",
        );
        test_err("default = 1", "expected string literal");
    }

    #[test]
    fn test_match_path() {
        fn test(path: Path, expect: &[&str], result: bool) {
            assert_eq!(match_path(&path, expect), result);
        }

        test(syn::parse_quote!(foo), &["foo"], true);
        test(syn::parse_quote!(foo<T>), &["foo"], true);
        test(syn::parse_quote!(foo::<T>), &["foo"], true);
        test(syn::parse_quote!(::foo), &["foo"], true);

        test(syn::parse_quote!(foo), &["spam", "egg", "foo"], true);
        test(syn::parse_quote!(foo<T>), &["spam", "egg", "foo"], true);
        test(syn::parse_quote!(foo::<T>), &["spam", "egg", "foo"], true);
        test(syn::parse_quote!(::foo), &["spam", "egg", "foo"], false);

        test(syn::parse_quote!(foo::bar), &["foo", "bar"], true);
        test(syn::parse_quote!(foo::bar<T>), &["foo", "bar"], true);
        test(syn::parse_quote!(foo::bar::<T>), &["foo", "bar"], true);
        test(syn::parse_quote!(foo<T>::bar), &["foo", "bar"], false);
        test(syn::parse_quote!(foo::<T>::bar), &["foo", "bar"], false);

        test(syn::parse_quote!(::foo::bar), &["foo", "bar"], true);
        test(syn::parse_quote!(::foo::bar<T>), &["foo", "bar"], true);
        test(syn::parse_quote!(::foo::bar::<T>), &["foo", "bar"], true);
        test(syn::parse_quote!(::foo<T>::bar), &["foo", "bar"], false);
        test(syn::parse_quote!(::foo::<T>::bar), &["foo", "bar"], false);

        test(syn::parse_quote!(foo), &["bar"], false);
        test(syn::parse_quote!(foo), &["foo", "bar"], false);
        test(syn::parse_quote!(foo::bar), &["foo"], false);
        test(syn::parse_quote!(foo::bar), &["bar"], false);
    }
}
