use syn::ext::IdentExt;
use syn::parse::{Parse, ParseStream};
use syn::punctuated::Punctuated;
use syn::{
    Attribute, Data, DataStruct, DeriveInput, Error, Field, Fields, Generics, Ident, LitStr, Path,
    QSelf, Token, Type, TypeGroup, TypeParen, TypePath, WhereClause, WherePredicate,
};

#[cfg_attr(test, derive(Debug, PartialEq))]
pub(crate) struct Codegen<'a> {
    pub(crate) ident: &'a Ident,
    pub(crate) generics: &'a Generics,

    pub(crate) fields: Vec<CodegenField<'a>>,

    pub(crate) insert_default: bool,
}

// TODO: Provide a `key_only` attribute for `bool` fields.
#[cfg_attr(test, derive(Debug, PartialEq))]
pub(crate) struct CodegenField<'a> {
    pub(crate) ident: &'a Ident,

    rename: Option<String>,

    pub(crate) container_type: ContainerType,

    pub(crate) insert_default: bool,
    pub(crate) insert_raw: bool,

    parse_with: Option<Path>,
    to_string_with: Option<Path>,
}

// NOTE: `Vec` is not supported, since `QueryBuilder` removes duplicate query keys.
#[derive(Clone, Copy, PartialEq)]
#[cfg_attr(test, derive(Debug))]
pub(crate) enum ContainerType {
    Map,
    Option,
    None,
}

impl Codegen<'_> {
    pub(crate) fn where_clause<'a, F>(&'a self, require_default: bool, f: F) -> Option<WhereClause>
    where
        F: FnMut(&'a Ident) -> WherePredicate,
    {
        let mut where_clause = self
            .generics
            .where_clause
            .clone()
            .unwrap_or_else(|| syn::parse_quote! { where });

        if require_default {
            where_clause
                .predicates
                .push(syn::parse_quote! { Self: ::std::default::Default });
        }

        where_clause.predicates.extend(self.type_params().map(f));

        (!where_clause.predicates.is_empty()).then_some(where_clause)
    }

    fn type_params(&self) -> impl Iterator<Item = &Ident> {
        self.generics.type_params().map(|param| &param.ident)
    }
}

impl CodegenField<'_> {
    pub(crate) fn key(&self) -> String {
        self.rename
            .clone()
            .unwrap_or_else(|| self.ident.unraw().to_string())
    }

    pub(crate) fn parse_with(&self) -> Option<&Path> {
        self.parse_with.as_ref()
    }

    pub(crate) fn to_string_with(&self) -> Option<&Path> {
        self.to_string_with.as_ref()
    }
}

type Args = Punctuated<Arg, Token![,]>;

#[cfg_attr(test, derive(Debug, PartialEq))]
enum Arg {
    Skip(Ident),
    Rename(Ident, String),
    InsertDefault(Ident),
    InsertRaw(Ident),
    With(Ident, Path),
    ParseWith(Ident, Path),
    ToStringWith(Ident, Path),
}

macro_rules! ensure_not_duplicated {
    ($value:ident, $span:expr $(,)?) => {
        if $value.is_some() {
            return Err(Error::new($span, "duplicated argument"));
        }
    };
}

impl<'a> Codegen<'a> {
    pub(crate) fn parse(input: &'a DeriveInput) -> Result<Self, Error> {
        let mut insert_default = None;
        for attr in &input.attrs {
            let Some(args) = try_parse_args(attr)? else {
                continue;
            };
            for arg in args {
                match arg {
                    Arg::InsertDefault(ident) => {
                        ensure_not_duplicated!(insert_default, ident.span());
                        insert_default = Some(true);
                    }
                    Arg::Skip(ident)
                    | Arg::Rename(ident, _)
                    | Arg::InsertRaw(ident)
                    | Arg::With(ident, _)
                    | Arg::ParseWith(ident, _)
                    | Arg::ToStringWith(ident, _) => {
                        return Err(Error::new(
                            ident.span(),
                            "cannot be applied at the struct level",
                        ));
                    }
                }
            }
        }

        let fields = match &input.data {
            Data::Struct(DataStruct {
                struct_token,
                fields,
                ..
            }) => match fields {
                Fields::Named(fields) => Ok(fields),
                _ => Err(struct_token.span),
            },
            Data::Enum(enum_) => Err(enum_.enum_token.span),
            Data::Union(union) => Err(union.union_token.span),
        }
        .map_err(|span| Error::new(span, "only named-field structs are supported"))?
        .named
        .iter()
        .filter_map(|field| CodegenField::try_parse(field).transpose())
        .try_collect::<Vec<_>>()?;

        let mut has_map = false;
        for field in &fields {
            if field.container_type == ContainerType::Map {
                if has_map {
                    return Err(Error::new(
                        field.ident.span(),
                        "support at most one map field",
                    ));
                }
                has_map = true;
            }
        }

        Ok(Self {
            ident: &input.ident,
            generics: &input.generics,
            fields,
            insert_default: insert_default.unwrap_or(false),
        })
    }
}

impl<'a> CodegenField<'a> {
    fn try_parse(field: &'a Field) -> Result<Option<Self>, Error> {
        let mut skip = None;
        let mut rename = None;
        let mut insert_default = None;
        let mut insert_raw = None;
        let mut parse_with = None;
        let mut to_string_with = None;
        for attr in &field.attrs {
            let Some(args) = try_parse_args(attr)? else {
                continue;
            };
            for arg in args {
                match arg {
                    Arg::Skip(ident) => {
                        ensure_not_duplicated!(skip, ident.span());
                        skip = Some(true);
                    }
                    Arg::Rename(ident, name) => {
                        ensure_not_duplicated!(rename, ident.span());
                        rename = Some(name);
                    }
                    Arg::InsertDefault(ident) => {
                        ensure_not_duplicated!(insert_default, ident.span());
                        insert_default = Some(true);
                    }
                    Arg::InsertRaw(ident) => {
                        ensure_not_duplicated!(insert_raw, ident.span());
                        insert_raw = Some(true);
                    }
                    Arg::With(ident, mut path) => {
                        ensure_not_duplicated!(parse_with, ident.span());
                        ensure_not_duplicated!(to_string_with, ident.span());
                        {
                            let mut path = path.clone();
                            path.segments.push(syn::parse_quote! { parse });
                            parse_with = Some(path);
                        }
                        path.segments.push(syn::parse_quote! { to_string });
                        to_string_with = Some(path);
                    }
                    Arg::ParseWith(ident, path) => {
                        ensure_not_duplicated!(parse_with, ident.span());
                        parse_with = Some(path);
                    }
                    Arg::ToStringWith(ident, path) => {
                        ensure_not_duplicated!(to_string_with, ident.span());
                        to_string_with = Some(path);
                    }
                }
            }
        }
        let insert_default = insert_default.unwrap_or(false);
        let insert_raw = insert_raw.unwrap_or(false);

        let ident = field.ident.as_ref().expect("named struct");
        let container_type = match_container_type(&field.ty);

        if rename.is_some() && container_type == ContainerType::Map {
            return Err(Error::new(
                ident.span(),
                "`rename` cannot be applied to a map field",
            ));
        }
        if insert_default && container_type != ContainerType::None {
            return Err(Error::new(
                ident.span(),
                "`insert_default` can only be applied to a scalar field",
            ));
        }

        if skip.unwrap_or(false) {
            return Ok(None);
        }

        Ok(Some(Self {
            ident,
            rename,
            container_type,
            insert_default,
            insert_raw,
            parse_with,
            to_string_with,
        }))
    }
}

const ATTR_NAME: &str = "g1_url";

const SKIP: &str = "skip";

const RENAME: &str = "rename";

const INSERT_DEFAULT: &str = "insert_default";
const INSERT_RAW: &str = "insert_raw";

const WITH: &str = "with";
const PARSE_WITH: &str = "parse_with";
const TO_STRING_WITH: &str = "to_string_with";

fn try_parse_args(attr: &Attribute) -> Result<Option<Args>, Error> {
    if attr.path().is_ident(ATTR_NAME) {
        attr.parse_args_with(Args::parse_terminated).map(Some)
    } else {
        Ok(None)
    }
}

impl Parse for Arg {
    fn parse(input: ParseStream<'_>) -> Result<Self, Error> {
        fn parse_string(input: ParseStream<'_>) -> Result<String, Error> {
            let _ = input.parse::<Token![=]>()?;
            let value = input.parse::<LitStr>()?;
            let string = value.value();
            if string.is_empty() {
                Err(Error::new(value.span(), "empty string"))
            } else {
                Ok(string)
            }
        }

        fn parse_path(input: ParseStream<'_>) -> Result<Path, Error> {
            let _ = input.parse::<Token![=]>()?;
            let value = input.parse::<LitStr>()?;
            let string = value.value();
            if string.is_empty() {
                Err(Error::new(value.span(), "empty path"))
            } else {
                syn::parse_str(&string).map_err(|_| Error::new(value.span(), "invalid path"))
            }
        }

        let name = input.parse()?;
        if name == SKIP {
            Ok(Self::Skip(name))
        } else if name == RENAME {
            Ok(Self::Rename(name, parse_string(input)?))
        } else if name == INSERT_DEFAULT {
            Ok(Self::InsertDefault(name))
        } else if name == INSERT_RAW {
            Ok(Self::InsertRaw(name))
        } else if name == WITH {
            Ok(Self::With(name, parse_path(input)?))
        } else if name == PARSE_WITH {
            Ok(Self::ParseWith(name, parse_path(input)?))
        } else if name == TO_STRING_WITH {
            Ok(Self::ToStringWith(name, parse_path(input)?))
        } else {
            Err(Error::new(name.span(), "unknown `g1_url` attribute"))
        }
    }
}

fn match_container_type(type_: &Type) -> ContainerType {
    const CONTAINER_TYPES: &[(&[&str], ContainerType)] = &[
        (&["std", "collections", "HashMap"], ContainerType::Map),
        (&["core", "collections", "HashMap"], ContainerType::Map),
        (&["std", "collections", "BTreeMap"], ContainerType::Map),
        (&["core", "collections", "BTreeMap"], ContainerType::Map),
        (&["std", "option", "Option"], ContainerType::Option),
        (&["core", "option", "Option"], ContainerType::Option),
    ];

    match type_ {
        Type::Group(TypeGroup { elem, .. }) | Type::Paren(TypeParen { elem, .. }) => {
            match_container_type(elem)
        }
        Type::Path(TypePath { qself, path }) => match qself {
            Some(QSelf { ty, .. }) => match_container_type(ty),
            None => CONTAINER_TYPES
                .iter()
                .copied()
                .find_map(|(expect, container_type)| {
                    match_path(path, expect).then_some(container_type)
                })
                .unwrap_or(ContainerType::None),
        },
        _ => ContainerType::None,
    }
}

// TODO: Refactor this into a common library.
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
    use std::fmt::Debug;

    use proc_macro2::Span;
    use syn::WhereClause;

    use super::*;

    fn i(name: &str) -> Ident {
        Ident::new(name, Span::call_site())
    }

    fn assert_ok<T>(result: Result<T, Error>, expect: T)
    where
        T: Debug + PartialEq,
    {
        assert_eq!(result.unwrap(), expect);
    }

    fn assert_err<T>(result: Result<T, Error>, error: &str)
    where
        T: Debug,
    {
        assert_eq!(result.unwrap_err().to_string(), error);
    }

    #[test]
    fn key() {
        let field = syn::parse_quote! { foo: () };
        let field = CodegenField::try_parse(&field).unwrap().unwrap();
        assert_eq!(field.key(), "foo");

        let field = syn::parse_quote! { r#try: () };
        let field = CodegenField::try_parse(&field).unwrap().unwrap();
        assert_eq!(field.key(), "try");

        let field = syn::parse_quote! {
            #[g1_url(rename = "spam egg")]
            r#try: ()
        };
        let field = CodegenField::try_parse(&field).unwrap().unwrap();
        assert_eq!(field.key(), "spam egg");
    }

    #[test]
    fn parse_with() {
        let field = syn::parse_quote! { x: u8 };
        let field = CodegenField::try_parse(&field).unwrap().unwrap();
        assert_eq!(field.parse_with(), None);

        let field = syn::parse_quote! {
            #[g1_url(with = "f::g")]
            x: u8
        };
        let field = CodegenField::try_parse(&field).unwrap().unwrap();
        assert_eq!(field.parse_with(), Some(&syn::parse_quote! { f::g::parse }));

        let field = syn::parse_quote! {
            #[g1_url(parse_with = "f::g")]
            x: u8
        };
        let field = CodegenField::try_parse(&field).unwrap().unwrap();
        assert_eq!(field.parse_with(), Some(&syn::parse_quote! { f::g }));
        assert_eq!(field.to_string_with(), None);
    }

    #[test]
    fn to_string_with() {
        let field = syn::parse_quote! { x: u8 };
        let field = CodegenField::try_parse(&field).unwrap().unwrap();
        assert_eq!(field.to_string_with(), None);

        let field = syn::parse_quote! {
            #[g1_url(with = "f::g")]
            x: u8
        };
        let field = CodegenField::try_parse(&field).unwrap().unwrap();
        assert_eq!(
            field.to_string_with(),
            Some(&syn::parse_quote! { f::g::to_string })
        );

        let field = syn::parse_quote! {
            #[g1_url(to_string_with = "f::g")]
            x: u8
        };
        let field = CodegenField::try_parse(&field).unwrap().unwrap();
        assert_eq!(field.to_string_with(), Some(&syn::parse_quote! { f::g }));
        assert_eq!(field.parse_with(), None);
    }

    #[test]
    fn codegen() {
        fn g(mut generics: Generics, where_clause: WhereClause) -> Generics {
            generics.where_clause = Some(where_clause);
            generics
        }

        assert_ok(
            Codegen::parse(&syn::parse_quote! {
                #[g1_url(insert_default)]
                struct Foo<K, V: Debug, T> where T: Iterator {
                    #[g1_url(parse_with = "f", to_string_with = "g")]
                    x: std::collections::BTreeMap<K, V>,

                    #[g1_url(rename = "spam egg")]
                    #[g1_url(with = "::p::q::<X>")]
                    y: Option<T>,

                    #[g1_url(insert_default)]
                    #[g1_url(insert_raw)]
                    r#try: T,

                    #[g1_url(skip)]
                    skipped: u64,
                }
            }),
            Codegen {
                ident: &i("Foo"),
                generics: &g(
                    syn::parse_quote!(<K, V: Debug, T>),
                    syn::parse_quote!(where T: Iterator),
                ),
                fields: vec![
                    CodegenField {
                        ident: &i("x"),
                        rename: None,
                        container_type: ContainerType::Map,
                        insert_default: false,
                        insert_raw: false,
                        parse_with: Some(syn::parse_quote! { f }),
                        to_string_with: Some(syn::parse_quote! { g }),
                    },
                    CodegenField {
                        ident: &i("y"),
                        rename: Some("spam egg".to_string()),
                        container_type: ContainerType::Option,
                        insert_default: false,
                        insert_raw: false,
                        parse_with: Some(syn::parse_quote! { ::p::q::<X>::parse }),
                        to_string_with: Some(syn::parse_quote! { ::p::q::<X>::to_string }),
                    },
                    CodegenField {
                        ident: &Ident::new_raw("try", Span::call_site()),
                        rename: None,
                        container_type: ContainerType::None,
                        insert_default: true,
                        insert_raw: true,
                        parse_with: None,
                        to_string_with: None,
                    },
                ],
                insert_default: true,
            },
        );
        assert_ok(
            Codegen::parse(&syn::parse_quote! { struct Foo {} }),
            Codegen {
                ident: &i("Foo"),
                generics: &syn::parse_quote!(),
                fields: Vec::new(),
                insert_default: false,
            },
        );

        assert_err(
            Codegen::parse(&syn::parse_quote! {
                #[g1_url(skip)]
                struct Foo {}
            }),
            "cannot be applied at the struct level",
        );
        assert_err(
            Codegen::parse(&syn::parse_quote! {
                #[g1_url(rename = "x")]
                struct Foo {}
            }),
            "cannot be applied at the struct level",
        );
        assert_err(
            Codegen::parse(&syn::parse_quote! {
                #[g1_url(insert_raw)]
                struct Foo {}
            }),
            "cannot be applied at the struct level",
        );
        assert_err(
            Codegen::parse(&syn::parse_quote! {
                #[g1_url(with = "x")]
                struct Foo {}
            }),
            "cannot be applied at the struct level",
        );
        assert_err(
            Codegen::parse(&syn::parse_quote! {
                #[g1_url(parse_with = "x")]
                struct Foo {}
            }),
            "cannot be applied at the struct level",
        );
        assert_err(
            Codegen::parse(&syn::parse_quote! {
                #[g1_url(to_string_with = "x")]
                struct Foo {}
            }),
            "cannot be applied at the struct level",
        );

        assert_err(
            Codegen::parse(&syn::parse_quote! {
                #[g1_url(insert_default)]
                #[g1_url(insert_default)]
                struct Foo {}
            }),
            "duplicated argument",
        );

        assert_err(
            Codegen::parse(&syn::parse_quote! { struct Foo; }),
            "only named-field structs are supported",
        );
        assert_err(
            Codegen::parse(&syn::parse_quote! { struct Foo(u8); }),
            "only named-field structs are supported",
        );
        assert_err(
            Codegen::parse(&syn::parse_quote! { enum Foo {} }),
            "only named-field structs are supported",
        );
        assert_err(
            Codegen::parse(&syn::parse_quote! { union Foo {} }),
            "only named-field structs are supported",
        );

        assert_err(
            Codegen::parse(&syn::parse_quote! {
                struct Foo {
                    x: HashMap<(), ()>,
                    y: (),
                    z: HashMap<(), ()>,
                }
            }),
            "support at most one map field",
        );
    }

    #[test]
    fn codegen_field() {
        assert_ok(
            CodegenField::try_parse(&syn::parse_quote! {
                #[g1_url(rename = "spam")]
                #[g1_url(with = "foo::<X>::bar", insert_raw)]
                r#try: Option<()>
            }),
            Some(CodegenField {
                ident: &Ident::new_raw("try", Span::call_site()),
                rename: Some("spam".to_string()),
                container_type: ContainerType::Option,
                insert_default: false,
                insert_raw: true,
                parse_with: Some(syn::parse_quote! { foo::<X>::bar::parse }),
                to_string_with: Some(syn::parse_quote! { foo::<X>::bar::to_string }),
            }),
        );
        assert_ok(
            CodegenField::try_parse(&syn::parse_quote! {
                #[g1_url(insert_default)]
                r#try: ()
            }),
            Some(CodegenField {
                ident: &Ident::new_raw("try", Span::call_site()),
                rename: None,
                container_type: ContainerType::None,
                insert_default: true,
                insert_raw: false,
                parse_with: None,
                to_string_with: None,
            }),
        );

        assert_ok(
            CodegenField::try_parse(&syn::parse_quote! {
                #[g1_url(rename = "spam", insert_default)]
                #[g1_url(skip)]
                r#try: ()
            }),
            None,
        );

        assert_err(
            CodegenField::try_parse(&syn::parse_quote! {
                #[g1_url(skip, insert_default, skip)]
                x: u8
            }),
            "duplicated argument",
        );
        assert_err(
            CodegenField::try_parse(&syn::parse_quote! {
                #[g1_url(rename = "x")]
                #[g1_url(skip, rename = "y")]
                x: u8
            }),
            "duplicated argument",
        );
        assert_err(
            CodegenField::try_parse(&syn::parse_quote! {
                #[g1_url(insert_default, insert_default)]
                x: u8
            }),
            "duplicated argument",
        );
        assert_err(
            CodegenField::try_parse(&syn::parse_quote! {
                #[g1_url(parse_with = "x", parse_with = "x")]
                x: u8
            }),
            "duplicated argument",
        );
        assert_err(
            CodegenField::try_parse(&syn::parse_quote! {
                #[g1_url(to_string_with = "x", to_string_with = "x")]
                x: u8
            }),
            "duplicated argument",
        );
        assert_err(
            CodegenField::try_parse(&syn::parse_quote! {
                #[g1_url(with = "x", with = "x")]
                x: u8
            }),
            "duplicated argument",
        );
        assert_err(
            CodegenField::try_parse(&syn::parse_quote! {
                #[g1_url(with = "x", parse_with = "x")]
                x: u8
            }),
            "duplicated argument",
        );
        assert_err(
            CodegenField::try_parse(&syn::parse_quote! {
                #[g1_url(with = "x", to_string_with = "x")]
                x: u8
            }),
            "duplicated argument",
        );

        assert_err(
            CodegenField::try_parse(&syn::parse_quote! {
                #[g1_url(rename = "foo")]
                x: HashMap<(), ()>
            }),
            "`rename` cannot be applied to a map field",
        );

        assert_err(
            CodegenField::try_parse(&syn::parse_quote! {
                #[g1_url(insert_default)]
                x: HashMap<(), ()>
            }),
            "`insert_default` can only be applied to a scalar field",
        );
        assert_err(
            CodegenField::try_parse(&syn::parse_quote! {
                #[g1_url(insert_default)]
                x: core::option::Option<()>
            }),
            "`insert_default` can only be applied to a scalar field",
        );
    }

    #[test]
    fn args() {
        fn args<const N: usize>(args: [Arg; N]) -> Args {
            args.into_iter().collect()
        }

        assert_ok(try_parse_args(&syn::parse_quote! { #[foo] }), None);

        assert_ok(
            try_parse_args(&syn::parse_quote! { #[g1_url()] }),
            Some(args([])),
        );
        assert_ok(
            try_parse_args(&syn::parse_quote! {
                #[g1_url(skip, rename = "try", skip, insert_default)]
            }),
            Some(args([
                Arg::Skip(i("skip")),
                Arg::Rename(i("rename"), "try".to_string()),
                Arg::Skip(i("skip")),
                Arg::InsertDefault(i("insert_default")),
            ])),
        );
    }

    #[test]
    fn arg() {
        assert_ok(syn::parse_str("skip"), Arg::Skip(i("skip")));

        assert_ok(
            syn::parse_str("rename = \"try\""),
            Arg::Rename(i("rename"), "try".to_string()),
        );

        assert_ok(
            syn::parse_str("insert_default"),
            Arg::InsertDefault(i("insert_default")),
        );

        assert_ok(
            syn::parse_str("with = \"foo::bar::<T>\""),
            Arg::With(i("with"), syn::parse_quote!(foo::bar::<T>)),
        );
        assert_ok(
            syn::parse_str("parse_with = \"foo::bar::<T>\""),
            Arg::ParseWith(i("parse_with"), syn::parse_quote!(foo::bar::<T>)),
        );
        assert_ok(
            syn::parse_str("to_string_with = \"foo::bar::<T>\""),
            Arg::ToStringWith(i("to_string_with"), syn::parse_quote!(foo::bar::<T>)),
        );

        assert_err(syn::parse_str::<Arg>("42"), "expected identifier");

        assert_err(syn::parse_str::<Arg>("foo"), "unknown `g1_url` attribute");
        assert_err(syn::parse_str::<Arg>("r#try"), "unknown `g1_url` attribute");

        for argname in ["rename", "with", "parse_with", "to_string_with"] {
            assert_err(syn::parse_str::<Arg>(argname), "expected `=`");
            assert_err(
                syn::parse_str::<Arg>(&format!("{argname} =")),
                "unexpected end of input, expected string literal",
            );
            assert_err(
                syn::parse_str::<Arg>(&format!("{argname} = foo")),
                "expected string literal",
            );
        }

        assert_err(syn::parse_str::<Arg>("rename = \"\""), "empty string");
        for argname in ["with", "parse_with", "to_string_with"] {
            assert_err(
                syn::parse_str::<Arg>(&format!("{argname} = \"\"")),
                "empty path",
            );
            assert_err(
                syn::parse_str::<Arg>(&format!("{argname} = \"1 + 2\"")),
                "invalid path",
            );
        }
    }

    #[test]
    fn test_match_container_type() {
        for (type_, expect) in [
            (syn::parse_quote!(HashMap<K, V>), ContainerType::Map),
            (
                syn::parse_quote!(std::collections::HashMap<K, V>),
                ContainerType::Map,
            ),
            (
                syn::parse_quote!(::std::collections::HashMap<K, V>),
                ContainerType::Map,
            ),
            (
                syn::parse_quote!(core::collections::BTreeMap<K, V>),
                ContainerType::Map,
            ),
            (
                syn::parse_quote!(::core::collections::BTreeMap<K, V>),
                ContainerType::Map,
            ),
            (syn::parse_quote!(Option<T>), ContainerType::Option),
            (
                syn::parse_quote!(std::option::Option<T>),
                ContainerType::Option,
            ),
            (
                syn::parse_quote!(::core::option::Option<T>),
                ContainerType::Option,
            ),
            (syn::parse_quote!(Result<T, E>), ContainerType::None),
            (syn::parse_quote!(u64), ContainerType::None),
        ] {
            assert_eq!(match_container_type(&type_), expect);
        }
    }
}
