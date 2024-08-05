use std::collections::{HashMap, HashSet};
use std::iter;

use proc_macro2::{Span, TokenStream};
use syn::parse::{Error, Parse, ParseStream};
use syn::punctuated::Punctuated;
use syn::{Expr, Ident, LitStr};

// Define `format!` and `write!` as procedural macros instead of declarative ones so that they can
// bypass `E0424` when accessing `self`.
#[proc_macro]
pub fn format(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    TokenStream::try_from(syn::parse_macro_input!(input as Format))
        .unwrap_or_else(Error::into_compile_error)
        .into()
}

#[proc_macro]
pub fn write(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    TokenStream::try_from(syn::parse_macro_input!(input as Write))
        .unwrap_or_else(Error::into_compile_error)
        .into()
}

#[proc_macro]
pub fn format_args(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    TokenStream::try_from(syn::parse_macro_input!(input as FormatArgs))
        .unwrap_or_else(Error::into_compile_error)
        .into()
}

struct Format(FormatArgs);

struct Write(Expr, FormatArgs);

#[cfg_attr(test, derive(Debug, Eq, PartialEq))]
struct FormatArgs {
    format: LitStr,
    argv: Punctuated<ArgValue, syn::Token![,]>,
}

#[cfg_attr(test, derive(Debug, Eq, PartialEq))]
enum ArgValue {
    Positional(Expr),
    Named(Ident, Expr),
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Arg<'a> {
    arg_ref: ArgRef<'a>,
    field: Vec<&'a str>,
    raw: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum ArgRef<'a> {
    Positional(usize),
    Named(&'a str),
}

impl Parse for Format {
    fn parse(input: ParseStream) -> Result<Self, Error> {
        Ok(Self(input.parse()?))
    }
}

impl Parse for Write {
    fn parse(input: ParseStream) -> Result<Self, Error> {
        let output = input.parse()?;
        input.parse::<syn::Token![,]>()?;
        Ok(Self(output, input.parse()?))
    }
}

impl Parse for FormatArgs {
    fn parse(input: ParseStream) -> Result<Self, Error> {
        // TODO: Consider supporting `std::include_str!`.
        let format = input.parse()?;
        if !input.is_empty() {
            input.parse::<syn::Token![,]>()?;
        }
        Ok(Self {
            format,
            argv: input.parse_terminated(ArgValue::parse, syn::Token![,])?,
        })
    }
}

impl Parse for ArgValue {
    fn parse(input: ParseStream) -> Result<Self, Error> {
        if input.peek(Ident) && input.peek2(syn::Token![=]) {
            let name = input.parse::<Ident>().expect("ident");
            input.parse::<syn::Token![=]>().expect("Token![=]");
            Ok(Self::Named(name, input.parse()?))
        } else {
            let expr = input.parse()?;
            if let Expr::Path(path) = &expr {
                if let Some(name) = path.path.get_ident() {
                    return Ok(Self::Named(name.clone(), expr));
                }
            }
            Ok(Self::Positional(expr))
        }
    }
}

impl ArgValue {
    fn name(&self) -> Option<&Ident> {
        match self {
            Self::Positional(_) => None,
            Self::Named(name, _) => Some(name),
        }
    }

    fn expr(&self) -> &Expr {
        match self {
            Self::Positional(expr) | Self::Named(_, expr) => expr,
        }
    }
}

// This accepts an extended format [syntax] that supports limited field access expressions.
// [syntax]: https://doc.rust-lang.org/std/fmt/#syntax
fn parse_format(mut format: &str) -> Result<(Vec<&str>, Vec<Arg>), &str> {
    let mut literals = Vec::new();
    let mut args = Vec::new();
    let mut index = iter::successors(Some(0), |i| Some(i + 1));

    let mut offset = 0;
    while !format.is_empty() {
        let Some(start) = format[offset..].find(['{', '}']) else {
            break;
        };

        match format.get(offset + start..offset + start + 2) {
            None => {
                return Err(&format[offset + start..]);
            }
            Some("{{" | "}}") => {
                offset += start + 2;
                continue;
            }
            Some(x) if x.starts_with("}") => {
                return Err(&format[offset + start..offset + start + 1]);
            }
            Some(x) => {
                assert!(x.starts_with("{"));
            }
        }

        let Some(mut end) = format[offset + start..].find('}') else {
            return Err(&format[offset + start..]);
        };
        end += start;

        let (_, arg, field, spec) = lazy_regex::regex_captures!(
            r"(?x)
            ^
            \s*
            (?:
                ( [[:digit:]]+ | [A-Za-z_][[:word:]]* )
                ( (?: \. (?: [[:digit:]]+ | [A-Za-z_][[:word:]]* ) )* )
            )?
            \s*
            ( : r? )?
            $
            ",
            &format[offset + start + 1..offset + end],
        )
        .ok_or(&format[offset + start..offset + end + 1])?;

        literals.push(&format[..offset + start]);
        format = &format[offset + end + 1..];
        offset = 0;

        args.push(Arg {
            arg_ref: if arg.is_empty() {
                ArgRef::Positional(index.next().expect("index"))
            } else if let Ok(i) = arg.parse() {
                ArgRef::Positional(i)
            } else {
                ArgRef::Named(arg)
            },
            field: field.split('.').filter(|f| !f.is_empty()).collect(),
            raw: spec == ":r",
        });
    }

    if !format.is_empty() {
        literals.push(format);
    }

    Ok((literals, args))
}

impl TryFrom<Format> for TokenStream {
    type Error = Error;

    fn try_from(Format(format_args): Format) -> Result<Self, Self::Error> {
        let format_args = TokenStream::try_from(format_args)?;
        Ok(quote::quote!(::g1_html::format(#format_args)))
    }
}

impl TryFrom<Write> for TokenStream {
    type Error = Error;

    fn try_from(Write(output, format_args): Write) -> Result<Self, Self::Error> {
        let format_args = TokenStream::try_from(format_args)?;
        Ok(quote::quote!(::g1_html::write(#output, #format_args)))
    }
}

impl TryFrom<FormatArgs> for TokenStream {
    type Error = Error;

    fn try_from(this: FormatArgs) -> Result<Self, Self::Error> {
        let format = this.format.value();
        let (literals, args) = parse_format(&format).map_err(|arg| {
            // TODO: Add more details to the error message.  Same below.
            Error::new(
                this.format.span(),
                std::format!("invalid format argument: {arg}"),
            )
        })?;

        let lookup: HashMap<_, _> = this
            .argv
            .iter()
            .enumerate()
            // TODO: How to turn an `Ident` into a string?
            .filter_map(|(i, argv)| argv.name().map(|n| (n.to_string(), i)))
            .collect();

        let mut arg_exprs = Vec::with_capacity(args.len());
        let mut unused_argv = HashSet::<usize>::from_iter(0..this.argv.len());
        for arg in &args {
            let argv_or_var = match arg.arg_ref {
                ArgRef::Positional(i) => Ok(i),
                ArgRef::Named(name) => match lookup.get(name) {
                    Some(i) => Ok(*i),
                    None => Err(name),
                },
            };
            let argv = match argv_or_var {
                Ok(i) => {
                    if i >= this.argv.len() {
                        return Err(Error::new(
                            this.format.span(),
                            std::format!("invalid positional argument: {i}"),
                        ));
                    }

                    unused_argv.remove(&i);

                    let expr = this.argv[i].expr();
                    quote::quote!((#expr))
                }
                Err(name) => {
                    let name = Ident::new(name, Span::call_site());
                    quote::quote!(#name)
                }
            };

            let field = arg.field.iter().map(|f| Ident::new(f, Span::call_site()));

            let spec = if arg.raw {
                quote::quote!(::g1_html::FormatSpec::Raw)
            } else {
                quote::quote!(::g1_html::FormatSpec::None)
            };

            arg_exprs.push(quote::quote!((& #argv #(.#field)*, #spec)));
        }

        if !unused_argv.is_empty() {
            return Err(Error::new(this.format.span(), "argument never used"));
        }

        Ok(quote::quote!(::g1_html::FormatArgs::new(&[#(#literals),*], &[#(#arg_exprs),*])))
    }
}

#[cfg(test)]
mod tests {
    use quote::quote as q;

    use super::*;

    macro_rules! arg {
        ($x:ident $a:literal $($f:literal)*) => {
            Arg {
                arg_ref: arg!(@arg_ref $x)($a),
                field: vec![$($f,)*],
                raw: arg!(@raw $x),
            }
        };

        (@arg_ref i) => { ArgRef::Positional };
        (@arg_ref I) => { ArgRef::Positional };
        (@arg_ref n) => { ArgRef::Named };
        (@arg_ref N) => { ArgRef::Named };

        (@raw i) => { false };
        (@raw I) => { true };
        (@raw n) => { false };
        (@raw N) => { true };
    }

    fn fa<const N: usize>(format: TokenStream, argv: [ArgValue; N]) -> FormatArgs {
        FormatArgs {
            format: syn::parse2(format).unwrap(),
            argv: argv.into_iter().collect(),
        }
    }

    fn p(expr: TokenStream) -> ArgValue {
        ArgValue::Positional(syn::parse2(expr).unwrap())
    }

    fn n(name: &str, expr: TokenStream) -> ArgValue {
        ArgValue::Named(
            Ident::new(name, Span::call_site()),
            syn::parse2(expr).unwrap(),
        )
    }

    #[test]
    fn parse_format_args() {
        fn test_ok(input: TokenStream, expect: FormatArgs) {
            let mut format_args: FormatArgs = syn::parse2(input).unwrap();
            format_args.argv.pop_punct(); // This makes testing easier.
            assert_eq!(format_args, expect);
        }

        fn test_err(input: TokenStream) {
            assert!(syn::parse2::<FormatArgs>(input).is_err());
        }

        test_ok(q!(""), fa(q!(""), []));
        test_ok(q!(r"",), fa(q!(r""), []));
        test_ok(q!(r#""#), fa(q!(r#""#), []));

        test_ok(q!("abc", 10), fa(q!("abc"), [p(q!(10))]));
        test_ok(q!("abc", 10,), fa(q!("abc"), [p(q!(10))]));

        test_ok(
            q!(r"\\", x, y = 1, ::a, a::b, p.q, self, z += 2),
            fa(
                q!(r"\\"),
                [
                    n("x", q!(x)),
                    n("y", q!(1)),
                    p(q!(::a)),
                    p(q!(a::b)),
                    p(q!(p.q)),
                    n("self", q!(self)),
                    p(q!(z += 2)),
                ],
            ),
        );

        test_err(q!());
        test_err(q!(0));
        test_err(q!(,));
    }

    #[test]
    fn parse_arg_value() {
        fn test_ok(input: TokenStream, expect: ArgValue) {
            assert_eq!(syn::parse2::<ArgValue>(input).unwrap(), expect);
        }

        fn test_err(input: TokenStream) {
            assert!(syn::parse2::<ArgValue>(input).is_err());
        }

        test_ok(q!("x"), p(q!("x")));
        test_ok(q!(x + 1), p(q!(x + 1)));
        test_ok(q!(x += 1), p(q!(x += 1)));
        test_ok(q!(f()), p(q!(f())));

        test_ok(q!(::a), p(q!(::a)));
        test_ok(q!(a::b), p(q!(a::b)));
        test_ok(q!(::a = 1), p(q!(::a = 1)));

        test_ok(q!(p.q), p(q!(p.q)));

        test_ok(q!(x), n("x", q!(x)));
        test_ok(q!(x = 1), n("x", q!(1)));
        test_ok(q!(self), n("self", q!(self)));

        test_err(q!());
        test_err(q!(,));
    }

    #[test]
    fn test_parse_format() {
        assert_eq!(parse_format(""), Ok((vec![], vec![])));
        assert_eq!(parse_format("abc"), Ok((vec!["abc"], vec![])));
        assert_eq!(parse_format("{{}}"), Ok((vec!["{{}}"], vec![])));
        assert_eq!(parse_format("   {{"), Ok((vec!["   {{"], vec![])));
        assert_eq!(parse_format("   }}"), Ok((vec!["   }}"], vec![])));
        assert_eq!(parse_format("abc{{def"), Ok((vec!["abc{{def"], vec![])));
        assert_eq!(parse_format("abc}}def"), Ok((vec!["abc}}def"], vec![])));
        assert_eq!(parse_format("x{{ y }}z"), Ok((vec!["x{{ y }}z"], vec![])));

        assert_eq!(parse_format("{}"), Ok((vec![""], vec![arg!(i 0)])));
        assert_eq!(parse_format("{   }"), Ok((vec![""], vec![arg!(i 0)])));
        assert_eq!(parse_format("{   :}"), Ok((vec![""], vec![arg!(i 0)])));
        assert_eq!(parse_format("{:r}"), Ok((vec![""], vec![arg!(I 0)])));
        assert_eq!(parse_format("{   :r}"), Ok((vec![""], vec![arg!(I 0)])));
        assert_eq!(
            parse_format("{{{}}}"),
            Ok((vec!["{{", "}}"], vec![arg!(i 0)]))
        );
        assert_eq!(
            parse_format("{}{:r}"),
            Ok((vec!["", ""], vec![arg!(i 0), arg!(I 1)])),
        );
        assert_eq!(
            parse_format("a{}b{:r}c"),
            Ok((vec!["a", "b", "c"], vec![arg!(i 0), arg!(I 1)])),
        );

        assert_eq!(parse_format("{0}"), Ok((vec![""], vec![arg!(i 0)])));
        assert_eq!(parse_format("{ 0 }"), Ok((vec![""], vec![arg!(i 0)])));
        assert_eq!(parse_format("{ 0 :}"), Ok((vec![""], vec![arg!(i 0)])));
        assert_eq!(parse_format("{1:r}"), Ok((vec![""], vec![arg!(I 1)])));
        assert_eq!(parse_format("{ 1 :r}"), Ok((vec![""], vec![arg!(I 1)])));
        assert_eq!(parse_format("{012}"), Ok((vec![""], vec![arg!(i 12)])));
        assert_eq!(
            parse_format("{2}{1:r}"),
            Ok((vec!["", ""], vec![arg!(i 2), arg!(I 1)])),
        );
        assert_eq!(
            parse_format("a{2}b{1 :r}c"),
            Ok((vec!["a", "b", "c"], vec![arg!(i 2), arg!(I 1)])),
        );

        assert_eq!(parse_format("{x}"), Ok((vec![""], vec![arg!(n "x")])));
        assert_eq!(parse_format("{ x :}"), Ok((vec![""], vec![arg!(n "x")])));
        assert_eq!(parse_format("{ x :r}"), Ok((vec![""], vec![arg!(N "x")])));
        assert_eq!(parse_format("{_}"), Ok((vec![""], vec![arg!(n "_")])));
        assert_eq!(
            parse_format("{x.y.z}"),
            Ok((vec![""], vec![arg!(n "x" "y" "z")])),
        );
        assert_eq!(
            parse_format("{ x.y.z }"),
            Ok((vec![""], vec![arg!(n "x" "y" "z")])),
        );
        assert_eq!(
            parse_format("{ x.y.z :r}"),
            Ok((vec![""], vec![arg!(N "x" "y" "z")])),
        );
        assert_eq!(
            parse_format("{x}{y:r}"),
            Ok((vec!["", ""], vec![arg!(n "x"), arg!(N "y")])),
        );
        assert_eq!(
            parse_format("a{x}b{y :r}c"),
            Ok((vec!["a", "b", "c"], vec![arg!(n "x"), arg!(N "y")])),
        );

        assert_eq!(
            parse_format("{{{ 2.x.1.y.0.z :}}}"),
            Ok((vec!["{{", "}}"], vec![arg!(i 2 "x" "1" "y" "0" "z")])),
        );
        assert_eq!(
            parse_format("{}{3}{x}{:r}{2:r}{a.b.c:r}"),
            Ok((
                vec!["", "", "", "", "", ""],
                vec![
                    arg!(i 0),
                    arg!(i 3),
                    arg!(n "x"),
                    arg!(I 1),
                    arg!(I 2),
                    arg!(N "a" "b" "c"),
                ],
            )),
        );

        assert_eq!(parse_format("   {"), Err("{"));
        assert_eq!(parse_format("   {abc"), Err("{abc"));
        assert_eq!(parse_format("   { { "), Err("{ { "));
        assert_eq!(parse_format("   { {}"), Err("{ {}"));
        assert_eq!(parse_format("   {{}"), Err("}"));
        assert_eq!(parse_format("   }"), Err("}"));
        assert_eq!(parse_format("   }   "), Err("}"));
        assert_eq!(parse_format("   } } "), Err("}"));

        assert_eq!(parse_format("{@}"), Err("{@}"));
        assert_eq!(parse_format("{0x1}"), Err("{0x1}"));
        assert_eq!(parse_format("{x.0x1}"), Err("{x.0x1}"));
        assert_eq!(parse_format("{x.y..z}"), Err("{x.y..z}"));

        assert_eq!(parse_format("{: }"), Err("{: }"));
        assert_eq!(parse_format("{:r }"), Err("{:r }"));
        assert_eq!(parse_format("{:?}"), Err("{:?}"));
    }

    #[test]
    fn generate() {
        fn test_ok(format_args: FormatArgs, expect: TokenStream) {
            assert_eq!(
                TokenStream::try_from(format_args).unwrap().to_string(),
                expect.to_string(),
            );
        }

        fn test_err(format_args: FormatArgs) {
            assert!(TokenStream::try_from(format_args).is_err());
        }

        test_ok(fa(q!(""), []), q!(::g1_html::FormatArgs::new(&[], &[])));
        test_ok(
            fa(q!("abc"), []),
            q!(::g1_html::FormatArgs::new(&["abc"], &[])),
        );

        test_ok(
            fa(q!("{{{}}}"), [p(q!(x))]),
            q!(::g1_html::FormatArgs::new(
                &["{{", "}}"],
                &[(&(x), ::g1_html::FormatSpec::None)]
            )),
        );
        test_ok(
            fa(q!("{}{:r}{:}"), [p(q!(x)), p(q!(y)), p(q!(z))]),
            q!(::g1_html::FormatArgs::new(
                &["", "", ""],
                &[
                    (&(x), ::g1_html::FormatSpec::None),
                    (&(y), ::g1_html::FormatSpec::Raw),
                    (&(z), ::g1_html::FormatSpec::None)
                ]
            )),
        );

        test_ok(
            fa(q!("{2}{0:r}{1:}"), [p(q!(x)), p(q!(y)), p(q!(z))]),
            q!(::g1_html::FormatArgs::new(
                &["", "", ""],
                &[
                    (&(z), ::g1_html::FormatSpec::None),
                    (&(x), ::g1_html::FormatSpec::Raw),
                    (&(y), ::g1_html::FormatSpec::None)
                ]
            )),
        );

        test_ok(
            fa(
                q!("{w}{x}{y.p.q:r}{z.a.b:}"),
                [n("x", q!(x)), n("y", q!(y))],
            ),
            q!(::g1_html::FormatArgs::new(
                &["", "", "", ""],
                &[
                    (&w, ::g1_html::FormatSpec::None),
                    (&(x), ::g1_html::FormatSpec::None),
                    (&(y).p.q, ::g1_html::FormatSpec::Raw),
                    (&z.a.b, ::g1_html::FormatSpec::None)
                ]
            )),
        );

        test_ok(
            fa(
                q!("a{}b{3}c{x}d{:r}e{2:r}f{a.b.c:r}g"),
                [n("x", q!(100)), p(q!(101)), p(q!(102)), p(q!(103))],
            ),
            q!(::g1_html::FormatArgs::new(
                &["a", "b", "c", "d", "e", "f", "g"],
                &[
                    (&(100), ::g1_html::FormatSpec::None),
                    (&(103), ::g1_html::FormatSpec::None),
                    (&(100), ::g1_html::FormatSpec::None),
                    (&(101), ::g1_html::FormatSpec::Raw),
                    (&(102), ::g1_html::FormatSpec::Raw),
                    (&a.b.c, ::g1_html::FormatSpec::Raw)
                ]
            )),
        );

        test_err(fa(q!("{x..y}"), [n("x", q!(100))]));

        test_err(fa(q!("{}"), []));
        test_err(fa(q!("{1}"), [p(q!(100))]));

        test_err(fa(q!(""), [p(q!(100))]));
    }
}
