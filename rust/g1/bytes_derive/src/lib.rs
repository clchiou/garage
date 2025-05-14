//! Generates decoders from `bytes::Buf` and encoders to `bytes::BufMut` for structs of primitive
//! types.
//!
//! TODO:
//! * Arrays or tuples of primitive types.
//! * Add attribute to skip fields (which will be initialized with default values).

#![feature(iterator_try_collect)]
#![feature(try_blocks)]
#![cfg_attr(test, feature(assert_matches))]

use heck::ToSnakeCase;
use proc_macro2::{Ident, TokenStream};
use syn::{
    ext::IdentExt, punctuated::Punctuated, token::Comma, Data, DataStruct, DeriveInput, Error,
    Field, Fields, Index, Visibility,
};

#[proc_macro_derive(BufExt, attributes(endian))]
pub fn derive_buf_ext(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    derive::<BufExt>(syn::parse_macro_input!(input as DeriveInput)).into()
}

#[proc_macro_derive(BufPeekExt, attributes(endian))]
pub fn derive_buf_peek_ext(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    derive::<BufPeekExt>(syn::parse_macro_input!(input as DeriveInput)).into()
}

#[proc_macro_derive(BufMutExt, attributes(endian))]
pub fn derive_buf_mut_ext(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    derive::<BufMutExt>(syn::parse_macro_input!(input as DeriveInput)).into()
}

const PRIMITIVE_TYPES: &[&str] = &[
    "u8", "i8", "u16", "i16", "u32", "i32", "u64", "i64", "u128", "i128", "f32", "f64",
];

const BIG_ENDIAN: &str = "";
const LITTLE_ENDIAN: &str = "_le";
const NATIVE_ENDIAN: &str = "_ne";

const DEFAULT_ENDIAN: &str = BIG_ENDIAN;

trait Generate {
    /// Generates code for an ordinary struct.
    fn gen(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error>;

    /// Generates code for a tuple struct.
    fn gen_tuple(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error>;

    /// Generates code for an unit struct.
    fn gen_unit(&self) -> TokenStream;

    /// Generates dummy code.
    fn gen_dummy(&self) -> TokenStream;
}

trait Target {
    fn new(snake_case: &str) -> Self;
}

struct Generator<'a, 'b, T> {
    vis: &'a Visibility,
    struct_name: &'a Ident,
    camel_case: Ident,
    default_endian: &'b str,
    target: T,
}

#[derive(Clone)]
struct BufExt {
    get: Ident,
    try_get: Ident,
}

#[derive(Clone)]
struct BufPeekExt {
    peek: Ident,
}

#[derive(Clone)]
struct BufMutExt {
    put: Ident,
}

fn derive<T>(input: DeriveInput) -> TokenStream
where
    T: Clone + Target,
    for<'a, 'b> Generator<'a, 'b, T>: Generate,
{
    let gen = Generator::<T>::new(&input);
    let output: Result<_, Error> = try {
        let gen = gen.with_default_endian(try_get_endian(&input)?);
        match &input.data {
            Data::Struct(DataStruct { fields, .. }) => match fields {
                Fields::Named(fields) => gen.gen(&fields.named)?,
                Fields::Unnamed(fields) => gen.gen_tuple(&fields.unnamed)?,
                Fields::Unit => gen.gen_unit(),
            },
            Data::Enum(_) | Data::Union(_) => Err(error::unsupported())?,
        }
    };
    output.unwrap_or_else(|error| {
        let dummy = gen.gen_dummy();
        let compile_errors = error.to_compile_error();
        quote::quote!(
            #dummy
            #compile_errors
        )
    })
}

fn try_get_endian(input: &DeriveInput) -> Result<&'static str, Error> {
    let mut iter = input.attrs.iter().filter_map(attr::try_get_endian);
    let endian = iter.next();
    if iter.next().is_some() {
        return Err(error::endian::duplicated());
    }
    endian.unwrap_or(Ok(DEFAULT_ENDIAN))
}

impl<'a, T> Generator<'a, '_, T>
where
    T: Target,
{
    fn new(input: &'a DeriveInput) -> Self {
        let camel_case = input.ident.unraw();
        let snake_case = camel_case.to_string().to_snake_case();
        Self {
            vis: &input.vis,
            struct_name: &input.ident,
            camel_case,
            default_endian: DEFAULT_ENDIAN,
            target: T::new(&snake_case),
        }
    }
}

impl Target for BufExt {
    fn new(snake_case: &str) -> Self {
        Self {
            get: quote::format_ident!("get_{}", snake_case),
            try_get: quote::format_ident!("try_get_{}", snake_case),
        }
    }
}

impl Target for BufPeekExt {
    fn new(snake_case: &str) -> Self {
        Self {
            peek: quote::format_ident!("peek_{}", snake_case),
        }
    }
}

impl Target for BufMutExt {
    fn new(snake_case: &str) -> Self {
        Self {
            put: quote::format_ident!("put_{}", snake_case),
        }
    }
}

impl<'a, 'b, T> Generator<'a, 'b, T>
where
    T: Clone,
{
    fn with_default_endian(&self, default_endian: &'b str) -> Generator<'a, 'b, T> {
        Generator {
            vis: self.vis,
            struct_name: self.struct_name,
            camel_case: self.camel_case.clone(),
            default_endian,
            target: self.target.clone(),
        }
    }
}

impl Generate for Generator<'_, '_, BufExt> {
    fn gen(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error> {
        Ok(self.gen_impl(self.gen_get(fields)?, self.gen_try_get(fields)?))
    }

    fn gen_tuple(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error> {
        Ok(self.gen_impl(self.gen_get_tuple(fields)?, self.gen_try_get(fields)?))
    }

    fn gen_unit(&self) -> TokenStream {
        let struct_name = &self.struct_name;
        self.gen_impl(
            quote::quote!(#struct_name),
            quote::quote!(Some(#struct_name)),
        )
    }

    fn gen_dummy(&self) -> TokenStream {
        self.gen_impl(
            quote::quote!(unimplemented!()),
            quote::quote!(unimplemented!()),
        )
    }
}

impl Generator<'_, '_, BufExt> {
    /// Generates a decoder for a struct.
    fn gen_impl(&self, get_body: TokenStream, try_get_body: TokenStream) -> TokenStream {
        let trait_name = quote::format_ident!("{}BufExt", self.camel_case);
        let get = &self.target.get;
        let try_get = &self.target.try_get;
        let vis = self.vis;
        let struct_name = self.struct_name;
        quote::quote! {
            #vis trait #trait_name: ::bytes::Buf {
                fn #get(&mut self) -> #struct_name {
                    #get_body
                }

                fn #try_get(&mut self) -> Option<#struct_name> {
                    #try_get_body
                }
            }

            impl<T> #trait_name for T where T: ::bytes::Buf {}
        }
    }

    /// Generates the body of the `get_foo` method for an ordinary struct.
    fn gen_get(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error> {
        let field = fields::gen_fields(fields)?;
        let get = fields::gen_gets(fields, self.default_endian)?;
        let struct_name = self.struct_name;
        Ok(quote::quote! {
            #(let #field = self.#get();)*
            #struct_name { #(#field),* }
        })
    }

    /// Generates the body of the `get_foo` method for a tuple struct.
    fn gen_get_tuple(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error> {
        let element = (0..fields.len())
            .map(|i| quote::format_ident!("e{}", i))
            .collect::<Vec<Ident>>();
        let get = fields::gen_gets(fields, self.default_endian)?;
        let struct_name = self.struct_name;
        Ok(quote::quote! {
            #(let #element = self.#get();)*
            #struct_name(#(#element),*)
        })
    }

    /// Generates the body of the `try_get_foo` method.
    fn gen_try_get(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error> {
        let size = fields::gen_size(fields)?;
        let get = &self.target.get;
        Ok(quote::quote! {
            #size
            if self.remaining() < SIZE {
                return None;
            }
            Some(self.#get())
        })
    }
}

impl Generate for Generator<'_, '_, BufPeekExt> {
    fn gen(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error> {
        Ok(self.gen_impl(self.gen_peek(fields)?))
    }

    fn gen_tuple(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error> {
        Ok(self.gen_impl(self.gen_peek_tuple(fields)?))
    }

    fn gen_unit(&self) -> TokenStream {
        let struct_name = &self.struct_name;
        self.gen_impl(quote::quote!(Some(#struct_name)))
    }

    fn gen_dummy(&self) -> TokenStream {
        self.gen_impl(quote::quote!(unimplemented!()))
    }
}

impl Generator<'_, '_, BufPeekExt> {
    /// Generates a decoder for a struct.
    fn gen_impl(&self, peek_body: TokenStream) -> TokenStream {
        let trait_name = quote::format_ident!("{}BufPeekExt", self.camel_case);
        let peek = &self.target.peek;
        let vis = self.vis;
        let struct_name = self.struct_name;
        quote::quote! {
            #vis trait #trait_name: ::g1_bytes::BufPeekExt {
                fn #peek(&self) -> Option<#struct_name> {
                    #peek_body
                }
            }

            impl<T> #trait_name for T where T: ::g1_bytes::BufPeekExt {}
        }
    }

    /// Generates the body of the `peek_foo` method for an ordinary struct.
    fn gen_peek(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error> {
        let size = fields::gen_size(fields)?;
        let field = fields::gen_fields(fields)?;
        let get = fields::gen_gets(fields, self.default_endian)?;
        let struct_name = self.struct_name;
        Ok(quote::quote! {
            #size
            let mut slice = self.peek_slice(SIZE)?;
            #(let #field = slice.#get();)*
            Some(#struct_name { #(#field),* })
        })
    }

    /// Generates the body of the `peek_foo` method for a tuple struct.
    fn gen_peek_tuple(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error> {
        let size = fields::gen_size(fields)?;
        let element = (0..fields.len())
            .map(|i| quote::format_ident!("e{}", i))
            .collect::<Vec<Ident>>();
        let get = fields::gen_gets(fields, self.default_endian)?;
        let struct_name = self.struct_name;
        Ok(quote::quote! {
            #size
            let mut slice = self.peek_slice(SIZE)?;
            #(let #element = slice.#get();)*
            Some(#struct_name(#(#element),*))
        })
    }
}

impl Generate for Generator<'_, '_, BufMutExt> {
    fn gen(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error> {
        Ok(self.gen_impl(self.gen_put(fields)?))
    }

    fn gen_tuple(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error> {
        Ok(self.gen_impl(self.gen_put_tuple(fields)?))
    }

    fn gen_unit(&self) -> TokenStream {
        self.gen_impl(quote::quote!())
    }

    fn gen_dummy(&self) -> TokenStream {
        self.gen_impl(quote::quote!(unimplemented!()))
    }
}

impl Generator<'_, '_, BufMutExt> {
    /// Generates an encoder for a struct.
    fn gen_impl(&self, put_body: TokenStream) -> TokenStream {
        let trait_name = quote::format_ident!("{}BufMutExt", self.camel_case);
        let put = &self.target.put;
        let vis = self.vis;
        let struct_name = self.struct_name;
        quote::quote! {
            #vis trait #trait_name: ::bytes::BufMut {
                fn #put(&mut self, this: &#struct_name) {
                    #put_body
                }
            }

            impl<T> #trait_name for T where T: ::bytes::BufMut {}
        }
    }

    /// Generates the body of the `put_foo` method for an ordinary struct.
    fn gen_put(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error> {
        let field = fields::gen_fields(fields)?;
        let put = fields::gen_puts(fields, self.default_endian)?;
        Ok(quote::quote! {
            #(self.#put(this.#field);)*
        })
    }

    /// Generates the body of the `put_foo` method for a tuple struct.
    fn gen_put_tuple(&self, fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error> {
        let element = (0..fields.len()).map(Index::from);
        let put = fields::gen_puts(fields, self.default_endian)?;
        Ok(quote::quote! {
            #(self.#put(this.#element);)*
        })
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use syn::FieldsNamed;

    use super::*;

    #[test]
    fn test_try_get_endian() {
        let input = syn::parse_quote! {
            struct Foo;
        };
        assert_matches!(try_get_endian(&input), Ok(""));

        let input = syn::parse_quote! {
            #[foo()]
            struct Foo;
        };
        assert_matches!(try_get_endian(&input), Ok(""));

        let input = syn::parse_quote! {
            #[endian("big")]
            struct Foo;
        };
        assert_matches!(try_get_endian(&input), Ok(""));

        let input = syn::parse_quote! {
            #[endian("little")]
            struct Foo;
        };
        assert_matches!(try_get_endian(&input), Ok("_le"));

        let input = syn::parse_quote! {
            #[endian("native")]
            struct Foo;
        };
        assert_matches!(try_get_endian(&input), Ok("_ne"));

        let input = syn::parse_quote! {
            #[endian("foo")]
            struct Foo;
        };
        let expect = error::endian::incorrect_value("foo").to_string();
        assert_matches!(try_get_endian(&input), Err(e) if e.to_string() == expect);

        let input = syn::parse_quote! {
            #[endian("little")]
            #[endian("big")]
            struct Foo;
        };
        let expect = error::endian::duplicated().to_string();
        assert_matches!(try_get_endian(&input), Err(e) if e.to_string() == expect);
    }

    #[test]
    fn gen_get() {
        let input = syn::parse_quote! {
            pub(in super::super) struct r#Foo;
        };
        let gen = Generator::<BufExt>::new(&input);

        let expect = quote::quote! {
            pub(in super::super) trait FooBufExt: ::bytes::Buf {
                fn get_foo(&mut self) -> r#Foo {
                    r#Foo
                }
                fn try_get_foo(&mut self) -> Option<r#Foo> {
                    Some(r#Foo)
                }
            }
            impl<T> FooBufExt for T where T: ::bytes::Buf {}
        }
        .to_string();
        assert_eq!(gen.gen_unit().to_string(), expect);

        let fields: FieldsNamed = syn::parse_quote!({
            ty_u8: u8,
        });
        let fields = fields.named;
        let expect = quote::quote! {
            let ty_u8 = self.get_u8();
            r#Foo { ty_u8 }
        }
        .to_string();
        assert_matches!(gen.gen_get(&fields), Ok(ts) if ts.to_string() == expect);
        let expect = quote::quote! {
            let e0 = self.get_u8();
            r#Foo(e0)
        }
        .to_string();
        assert_matches!(gen.gen_get_tuple(&fields), Ok(ts) if ts.to_string() == expect);
        let expect = quote::quote! {
            const SIZE: usize = ::std::mem::size_of::<u8>();
            if self.remaining() < SIZE {
                return None;
            }
            Some(self.get_foo())
        }
        .to_string();
        assert_matches!(gen.gen_try_get(&fields), Ok(ts) if ts.to_string() == expect);

        let fields: FieldsNamed = syn::parse_quote!({
            ty_u8: u8,
            ty_i8: i8,
        });
        let fields = fields.named;
        let expect = quote::quote! {
            let ty_u8 = self.get_u8();
            let ty_i8 = self.get_i8();
            r#Foo { ty_u8, ty_i8 }
        }
        .to_string();
        assert_matches!(gen.gen_get(&fields), Ok(ts) if ts.to_string() == expect);
        let expect = quote::quote! {
            let e0 = self.get_u8();
            let e1 = self.get_i8();
            r#Foo(e0, e1)
        }
        .to_string();
        assert_matches!(gen.gen_get_tuple(&fields), Ok(ts) if ts.to_string() == expect);
        let expect = quote::quote! {
            const SIZE: usize = ::std::mem::size_of::<u8>() + ::std::mem::size_of::<i8>();
            if self.remaining() < SIZE {
                return None;
            }
            Some(self.get_foo())
        }
        .to_string();
        assert_matches!(gen.gen_try_get(&fields), Ok(ts) if ts.to_string() == expect);
    }

    #[test]
    fn gen_peek() {
        let input = syn::parse_quote! {
            pub(in super::super) struct r#FooBar;
        };
        let gen = Generator::<BufPeekExt>::new(&input);

        let expect = quote::quote! {
            pub(in super::super) trait FooBarBufPeekExt: ::g1_bytes::BufPeekExt {
                fn peek_foo_bar(&self) -> Option<r#FooBar> {
                    Some(r#FooBar)
                }
            }
            impl<T> FooBarBufPeekExt for T where T: ::g1_bytes::BufPeekExt {}
        }
        .to_string();
        assert_eq!(gen.gen_unit().to_string(), expect);

        let fields: FieldsNamed = syn::parse_quote!({
            ty_u8: u8,
        });
        let fields = fields.named;
        let expect = quote::quote! {
            const SIZE: usize = ::std::mem::size_of::<u8>();
            let mut slice = self.peek_slice(SIZE)?;
            let ty_u8 = slice.get_u8();
            Some(r#FooBar { ty_u8 })
        }
        .to_string();
        assert_matches!(gen.gen_peek(&fields), Ok(ts) if ts.to_string() == expect);
        let expect = quote::quote! {
            const SIZE: usize = ::std::mem::size_of::<u8>();
            let mut slice = self.peek_slice(SIZE)?;
            let e0 = slice.get_u8();
            Some(r#FooBar(e0))
        }
        .to_string();
        assert_matches!(gen.gen_peek_tuple(&fields), Ok(ts) if ts.to_string() == expect);

        let fields: FieldsNamed = syn::parse_quote!({
            ty_u8: u8,
            ty_i8: i8,
        });
        let fields = fields.named;
        let expect = quote::quote! {
            const SIZE: usize = ::std::mem::size_of::<u8>() + ::std::mem::size_of::<i8>();
            let mut slice = self.peek_slice(SIZE)?;
            let ty_u8 = slice.get_u8();
            let ty_i8 = slice.get_i8();
            Some(r#FooBar { ty_u8, ty_i8 })
        }
        .to_string();
        assert_matches!(gen.gen_peek(&fields), Ok(ts) if ts.to_string() == expect);
        let expect = quote::quote! {
            const SIZE: usize = ::std::mem::size_of::<u8>() + ::std::mem::size_of::<i8>();
            let mut slice = self.peek_slice(SIZE)?;
            let e0 = slice.get_u8();
            let e1 = slice.get_i8();
            Some(r#FooBar(e0, e1))
        }
        .to_string();
        assert_matches!(gen.gen_peek_tuple(&fields), Ok(ts) if ts.to_string() == expect);
    }

    #[test]
    fn gen_put() {
        let input = syn::parse_quote! {
            pub(in super::super) struct r#Foo;
        };
        let gen = Generator::<BufMutExt>::new(&input);

        let expect = quote::quote! {
            pub(in super::super) trait FooBufMutExt: ::bytes::BufMut {
                fn put_foo(&mut self, this: &r#Foo) {}
            }
            impl<T> FooBufMutExt for T where T: ::bytes::BufMut {}
        }
        .to_string();
        assert_eq!(gen.gen_unit().to_string(), expect);

        let fields: FieldsNamed = syn::parse_quote!({
            ty_u8: u8,
        });
        let fields = fields.named;
        let expect = quote::quote! {
            self.put_u8(this.ty_u8);
        }
        .to_string();
        assert_matches!(gen.gen_put(&fields), Ok(ts) if ts.to_string() == expect);
        let expect = quote::quote! {
            self.put_u8(this.0);
        }
        .to_string();
        assert_matches!(gen.gen_put_tuple(&fields), Ok(ts) if ts.to_string() == expect);

        let fields: FieldsNamed = syn::parse_quote!({
            ty_u8: u8,
            ty_i8: i8,
        });
        let fields = fields.named;
        let expect = quote::quote! {
            self.put_u8(this.ty_u8);
            self.put_i8(this.ty_i8);
        }
        .to_string();
        assert_matches!(gen.gen_put(&fields), Ok(ts) if ts.to_string() == expect);
        let expect = quote::quote! {
            self.put_u8(this.0);
            self.put_i8(this.1);
        }
        .to_string();
        assert_matches!(gen.gen_put_tuple(&fields), Ok(ts) if ts.to_string() == expect);
    }
}

pub(crate) mod fields {
    use proc_macro2::{Ident, TokenStream};
    use syn::{punctuated::Punctuated, token::Comma, Error, Field};

    use crate::{error, field};

    /// Generates the field name for each struct field.
    pub(crate) fn gen_fields(fields: &Punctuated<Field, Comma>) -> Result<Vec<&Ident>, Error> {
        assert!(!fields.is_empty());
        fields
            .iter()
            .map(|field| field.ident.as_ref())
            .try_collect::<Vec<&Ident>>()
            .ok_or_else(error::unnamed_field)
    }

    /// Generates the get method name for each struct field.
    pub(crate) fn gen_gets(
        fields: &Punctuated<Field, Comma>,
        default_endian: &str,
    ) -> Result<Vec<Ident>, Error> {
        assert!(!fields.is_empty());
        fields
            .iter()
            .map(|field| field::gen_get(field, default_endian))
            .try_collect()
    }

    /// Generates the put method name for each struct field.
    pub(crate) fn gen_puts(
        fields: &Punctuated<Field, Comma>,
        default_endian: &str,
    ) -> Result<Vec<Ident>, Error> {
        assert!(!fields.is_empty());
        fields
            .iter()
            .map(|field| field::gen_put(field, default_endian))
            .try_collect()
    }

    /// Generates the struct size expression.
    pub(crate) fn gen_size(fields: &Punctuated<Field, Comma>) -> Result<TokenStream, Error> {
        assert!(!fields.is_empty());
        let types = fields
            .iter()
            .map(field::try_get_type)
            .try_collect::<Vec<&Ident>>()?;
        Ok(quote::quote! {
            const SIZE: usize = #(::std::mem::size_of::<#types>())+*;
        })
    }

    #[cfg(test)]
    mod tests {
        use std::assert_matches::assert_matches;

        use syn::FieldsNamed;

        use crate::{BIG_ENDIAN, LITTLE_ENDIAN};

        use super::*;

        #[test]
        fn test_gen_fields() {
            let fields: FieldsNamed = syn::parse_quote!({
                ty_u8: u8,
            });
            let fields = fields.named;
            let expect = vec!["ty_u8"];
            assert_matches!(gen_fields(&fields), Ok(fields) if fields == expect);

            let fields: FieldsNamed = syn::parse_quote!({
                ty_u8: u8,
                ty_i8: i8,
            });
            let fields = fields.named;
            let expect = vec!["ty_u8", "ty_i8"];
            assert_matches!(gen_fields(&fields), Ok(fields) if fields == expect);

            let fields: FieldsNamed = syn::parse_quote!({
                vec: Vec<u8>,
            });
            let fields = fields.named;
            let expect = vec!["vec"];
            assert_matches!(gen_fields(&fields), Ok(fields) if fields == expect);
        }

        #[test]
        #[should_panic(expected = "assertion failed: !fields.is_empty()")]
        fn test_gen_fields_empty() {
            let fields: FieldsNamed = syn::parse_quote!({});
            let fields = fields.named;
            let _ = gen_fields(&fields);
        }

        #[test]
        fn test_gen_method_names() {
            let fields: FieldsNamed = syn::parse_quote!({
                ty_u8: u8,
            });
            let fields = fields.named;
            let expect = vec!["get_u8"];
            assert_matches!(gen_gets(&fields, BIG_ENDIAN), Ok(gets) if gets == expect);
            let expect = vec!["put_u8"];
            assert_matches!(gen_puts(&fields, BIG_ENDIAN), Ok(puts) if puts == expect);

            let fields: FieldsNamed = syn::parse_quote!({
                ty_u8: u8,

                #[endian("native")]
                ty_i8: i8,
            });
            let fields = fields.named;
            let expect = vec!["get_u8_le", "get_i8_ne"];
            assert_matches!(gen_gets(&fields, LITTLE_ENDIAN), Ok(gets) if gets == expect);
            let expect = vec!["put_u8_le", "put_i8_ne"];
            assert_matches!(gen_puts(&fields, LITTLE_ENDIAN), Ok(puts) if puts == expect);

            let fields: FieldsNamed = syn::parse_quote!({
                vec: Vec<u8>,
            });
            let fields = fields.named;
            assert_matches!(gen_gets(&fields, BIG_ENDIAN), Err(_));
            assert_matches!(gen_puts(&fields, BIG_ENDIAN), Err(_));
        }

        #[test]
        #[should_panic(expected = "assertion failed: !fields.is_empty()")]
        fn test_gen_gets_empty() {
            let fields: FieldsNamed = syn::parse_quote!({});
            let fields = fields.named;
            let _ = gen_gets(&fields, BIG_ENDIAN);
        }

        #[test]
        #[should_panic(expected = "assertion failed: !fields.is_empty()")]
        fn test_gen_puts_empty() {
            let fields: FieldsNamed = syn::parse_quote!({});
            let fields = fields.named;
            let _ = gen_puts(&fields, BIG_ENDIAN);
        }

        #[test]
        fn test_gen_size() {
            let fields: FieldsNamed = syn::parse_quote!({
                ty_u8: u8,
            });
            let fields = fields.named;
            let expect = quote::quote! {
                const SIZE: usize = ::std::mem::size_of::<u8>();
            }
            .to_string();
            assert_matches!(gen_size(&fields), Ok(ts) if ts.to_string() == expect);

            let fields: FieldsNamed = syn::parse_quote!({
                ty_u8: u8,
                ty_i8: i8,
            });
            let fields = fields.named;
            let expect = quote::quote! {
                const SIZE: usize = ::std::mem::size_of::<u8>() + ::std::mem::size_of::<i8>();
            }
            .to_string();
            assert_matches!(gen_size(&fields), Ok(ts) if ts.to_string() == expect);

            let fields: FieldsNamed = syn::parse_quote!({
                vec: Vec<u8>,
            });
            let fields = fields.named;
            assert_matches!(gen_size(&fields), Err(_));
        }

        #[test]
        #[should_panic(expected = "assertion failed: !fields.is_empty()")]
        fn test_gen_size_empty() {
            let fields: FieldsNamed = syn::parse_quote!({});
            let fields = fields.named;
            let _ = gen_size(&fields);
        }
    }
}

pub(crate) mod field {
    use proc_macro2::Ident;
    use syn::{Error, Field, Type, TypePath};

    use crate::{attr, error, PRIMITIVE_TYPES};

    /// Generates the get method name for the field.
    pub(crate) fn gen_get(field: &Field, default_endian: &str) -> Result<Ident, Error> {
        gen_method_name(field, "get", default_endian)
    }

    /// Generates the put method name for the field.
    pub(crate) fn gen_put(field: &Field, default_endian: &str) -> Result<Ident, Error> {
        gen_method_name(field, "put", default_endian)
    }

    fn gen_method_name(field: &Field, method: &str, default_endian: &str) -> Result<Ident, Error> {
        let ty = try_get_type(field)?;
        let endian = try_get_endian(field).unwrap_or(Ok(default_endian))?;
        Ok(quote::format_ident!("{}_{}{}", method, ty, endian))
    }

    /// Returns the type of the field.
    ///
    /// It errs if the type is not a primitive type.
    pub(crate) fn try_get_type(field: &Field) -> Result<&Ident, Error> {
        if let Type::Path(TypePath { qself: None, path }) = &field.ty {
            let ident = path
                .get_ident()
                .ok_or_else(|| error::unsupported_type(&field.ty))?;
            // We cannot load `PRIMITIVE_TYPES` into a `HashSet` via `Once` because, for some
            // reason, doing so causes rustc to crash due to use-after-free.
            if PRIMITIVE_TYPES.iter().any(|ty| ident == ty) {
                return Ok(ident);
            }
        }
        Err(error::unsupported_type(&field.ty))
    }

    /// Returns the endian value of the field or `None` if the endian attribute is not specified.
    ///
    /// It errs if the endian value is incorrect.
    fn try_get_endian(field: &Field) -> Option<Result<&'static str, Error>> {
        let mut iter = field.attrs.iter().filter_map(attr::try_get_endian);
        let endian = iter.next();
        if iter.next().is_some() {
            return Some(Err(error::endian::duplicated()));
        }
        endian
    }

    #[cfg(test)]
    mod tests {
        use std::assert_matches::assert_matches;

        use syn::FieldsNamed;

        use crate::{error, BIG_ENDIAN, LITTLE_ENDIAN};

        use super::*;

        #[test]
        fn test_gen_method_name() {
            let fields: FieldsNamed = syn::parse_quote!({
                ty_u8: u8,

                #[endian("big")]
                ty_i8: i8,

                #[endian("little")]
                ty_u16: u16,

                #[endian("native")]
                ty_i16: i16,
            });
            let fields = fields.named;

            assert_matches!(gen_get(&fields[0], BIG_ENDIAN), Ok(get) if get == "get_u8");
            assert_matches!(gen_get(&fields[0], LITTLE_ENDIAN), Ok(get) if get == "get_u8_le");
            assert_matches!(gen_get(&fields[1], LITTLE_ENDIAN), Ok(get) if get == "get_i8");
            assert_matches!(gen_get(&fields[2], BIG_ENDIAN), Ok(get) if get == "get_u16_le");
            assert_matches!(gen_get(&fields[3], BIG_ENDIAN), Ok(get) if get == "get_i16_ne");

            assert_matches!(gen_put(&fields[0], BIG_ENDIAN), Ok(put) if put == "put_u8");
            assert_matches!(gen_put(&fields[0], LITTLE_ENDIAN), Ok(put) if put == "put_u8_le");
            assert_matches!(gen_put(&fields[1], LITTLE_ENDIAN), Ok(put) if put == "put_i8");
            assert_matches!(gen_put(&fields[2], BIG_ENDIAN), Ok(put) if put == "put_u16_le");
            assert_matches!(gen_put(&fields[3], BIG_ENDIAN), Ok(put) if put == "put_i16_ne");
        }

        #[test]
        fn test_try_get_type() {
            let fields: FieldsNamed = syn::parse_quote!({
                ty_u8: u8,
                ty_i8: i8,
                ty_u16: u16,
                ty_i16: i16,
                ty_u32: u32,
                ty_i32: i32,
                ty_u64: u64,
                ty_i64: i64,
                ty_u128: u128,
                ty_i128: i128,
                ty_f32: f32,
                ty_f64: f64,
            });
            let fields = fields.named;
            assert_eq!(fields.len(), PRIMITIVE_TYPES.len());
            for (field, expect) in fields.iter().zip(PRIMITIVE_TYPES.iter()) {
                assert_matches!(try_get_type(field), Ok(ident) if ident == expect);
            }

            let fields: FieldsNamed = syn::parse_quote!({
                unit: (),
                array: [u8; 0],
                tuple: (u8, u8),
                vec: Vec<u8>,
                slice: &[u8],
            });
            let fields = fields.named;
            for field in &fields {
                let expect = error::unsupported_type(&field.ty).to_string();
                assert_matches!(try_get_type(field), Err(e) if e.to_string() == expect);
            }
        }

        #[test]
        fn test_try_get_endian() {
            let fields: FieldsNamed = syn::parse_quote!({
                no_attr: u8,

                #[foo()]
                other_attr: u8,

                #[endian("little")]
                has_attr: u8,

                #[endian("native")]
                #[endian("big")]
                duplicated_attr: u8,
            });
            let fields = fields.named;

            assert_matches!(try_get_endian(&fields[0]), None);
            assert_matches!(try_get_endian(&fields[1]), None);

            assert_matches!(try_get_endian(&fields[2]), Some(Ok("_le")));

            let expect = error::endian::duplicated().to_string();
            assert_matches!(try_get_endian(&fields[3]), Some(Err(e)) if e.to_string() == expect);
        }
    }
}

pub(crate) mod attr {
    use syn::{Attribute, Error, Expr, Lit};

    use crate::{error, BIG_ENDIAN, LITTLE_ENDIAN, NATIVE_ENDIAN};

    /// Returns the endian value of the attribute or `None` if the attribute is not an endian
    /// attribute.
    ///
    /// It errs if the endian value is incorrect.
    pub(crate) fn try_get_endian(attr: &Attribute) -> Option<Result<&'static str, Error>> {
        if !attr.path().is_ident("endian") {
            return None;
        }
        Some(
            try {
                match try_get_string_literal(&attr.parse_args::<Expr>()?)
                    .ok_or_else(error::endian::non_string_literal)?
                    .as_str()
                {
                    "big" => BIG_ENDIAN,
                    "little" => LITTLE_ENDIAN,
                    "native" => NATIVE_ENDIAN,
                    endian => Err(error::endian::incorrect_value(endian))?,
                }
            },
        )
    }

    /// Returns the string value of a string literal expression.
    fn try_get_string_literal(expr: &Expr) -> Option<String> {
        if let Expr::Lit(lit) = expr {
            if let Lit::Str(lit) = &lit.lit {
                return Some(lit.value());
            }
        }
        None
    }

    #[cfg(test)]
    mod tests {
        use std::assert_matches::assert_matches;

        use crate::error;

        use super::*;

        #[test]
        fn test_try_get_endian() {
            fn test_ok(attr: &Attribute, expect: &str) {
                assert_matches!(try_get_endian(attr), Some(Ok(endian)) if endian == expect);
            }

            fn test_err(attr: &Attribute, expect: &str) {
                assert_matches!(try_get_endian(attr), Some(Err(e)) if e.to_string() == expect);
            }

            assert!(try_get_endian(&syn::parse_quote!(#[foo()])).is_none());

            test_ok(&syn::parse_quote!(#[endian("big")]), "");
            test_ok(&syn::parse_quote!(#[endian("little")]), "_le");
            test_ok(&syn::parse_quote!(#[endian("native")]), "_ne");

            test_err(
                &syn::parse_quote!(#[endian()]),
                "unexpected end of input, expected an expression",
            );
            test_err(
                &syn::parse_quote!(#[endian(1)]),
                &error::endian::non_string_literal().to_string(),
            );
            test_err(
                &syn::parse_quote!(#[endian("foo")]),
                &error::endian::incorrect_value("foo").to_string(),
            );
        }

        #[test]
        fn test_try_get_string_literal() {
            fn test(expr: &str, expect: Option<&str>) {
                assert_eq!(
                    try_get_string_literal(&syn::parse_str(expr).unwrap()),
                    expect.map(String::from),
                );
            }

            test("\"\"", Some(""));
            test("\"hello world\"", Some("hello world"));
            test("u8", None);
            test("42", None);
        }
    }
}

pub(crate) mod error {
    use proc_macro2::Span;
    use syn::{Error, Type};

    fn new_error(message: &str) -> Error {
        Error::new(Span::call_site(), message)
    }

    pub(crate) fn unsupported() -> Error {
        new_error("`#[derive(BufExt)]` and `#[derive(BufMutExt)]` only supports struct")
    }

    pub(crate) fn unsupported_type(ty: &Type) -> Error {
        const MESSAGE: &str =
            "`#[derive(BufExt)]` and `#[derive(BufMutExt)]` only supports primitive types";
        new_error(&format!("{}: {}", MESSAGE, quote::quote!(#ty)))
    }

    pub(crate) fn unnamed_field() -> Error {
        new_error("struct field is unnamed")
    }

    pub(crate) mod endian {
        use syn::Error;

        use super::new_error;

        pub(crate) fn duplicated() -> Error {
            new_error("`#[endian(...)]` can only be specified at most once per struct or per field")
        }

        pub(crate) fn non_string_literal() -> Error {
            new_error("`#[endian(...)]` should be a string literal")
        }

        pub(crate) fn incorrect_value(endian: &str) -> Error {
            const MESSAGE: &str =
                "`#[endian(...)]` should be one of \"big\", \"little\", or \"native\"";
            new_error(&format!("{MESSAGE}: \"{endian}\""))
        }
    }
}
