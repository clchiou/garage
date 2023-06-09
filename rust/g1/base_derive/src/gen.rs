use proc_macro2::TokenStream;
use syn::{ConstParam, DeriveInput, Field, GenericParam, Index, LifetimeParam, TypeParam};

pub(crate) fn generic_params(input: &DeriveInput) -> TokenStream {
    if input.generics.params.is_empty() {
        TokenStream::new()
    } else {
        let generic_params = &input.generics.params;
        quote::quote!(<#generic_params>)
    }
}

pub(crate) fn generic_param_names(input: &DeriveInput) -> TokenStream {
    if input.generics.params.is_empty() {
        TokenStream::new()
    } else {
        let names: Vec<TokenStream> = input
            .generics
            .params
            .iter()
            .map(|param| match param {
                GenericParam::Lifetime(LifetimeParam { lifetime, .. }) => quote::quote!(#lifetime),
                GenericParam::Type(TypeParam { ident, .. }) => quote::quote!(#ident),
                GenericParam::Const(ConstParam { ident, .. }) => quote::quote!(#ident),
            })
            .collect();
        quote::quote!(<#(#names),*>)
    }
}

pub(crate) fn where_clause(input: &DeriveInput) -> TokenStream {
    input
        .generics
        .where_clause
        .as_ref()
        .map(|where_clause| quote::quote!(#where_clause))
        .unwrap_or_else(TokenStream::new)
}

pub(crate) fn field(index: usize, field: &Field) -> TokenStream {
    match field.ident.as_ref() {
        Some(field) => quote::quote!(#field),
        None => {
            let index = Index::from(index);
            quote::quote!(#index)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test() {
        let input: DeriveInput = syn::parse_quote! {
            struct Foo {}
        };
        assert_eq!(
            generic_params(&input).to_string(),
            TokenStream::new().to_string(),
        );
        assert_eq!(
            generic_param_names(&input).to_string(),
            TokenStream::new().to_string(),
        );
        assert_eq!(
            where_clause(&input).to_string(),
            TokenStream::new().to_string(),
        );

        let input: DeriveInput = syn::parse_quote! {
            struct Foo<'a, T, const N: usize> {}
        };
        assert_eq!(
            generic_params(&input).to_string(),
            quote::quote!(<'a, T, const N: usize>).to_string(),
        );
        assert_eq!(
            generic_param_names(&input).to_string(),
            quote::quote!(<'a, T, N>).to_string(),
        );
        assert_eq!(
            where_clause(&input).to_string(),
            TokenStream::new().to_string(),
        );

        let input: DeriveInput = syn::parse_quote! {
            struct Foo<'a: 'static, T: fmt::Debug, const N: usize> {}
        };
        assert_eq!(
            generic_params(&input).to_string(),
            quote::quote!(<'a: 'static, T: fmt::Debug, const N: usize>).to_string(),
        );
        assert_eq!(
            generic_param_names(&input).to_string(),
            quote::quote!(<'a, T, N>).to_string(),
        );
        assert_eq!(
            where_clause(&input).to_string(),
            TokenStream::new().to_string()
        );

        let input: DeriveInput = syn::parse_quote! {
            struct Foo<'a, T> where 'a: 'static, T: fmt::Debug {}
        };
        assert_eq!(
            generic_params(&input).to_string(),
            quote::quote!(<'a, T>).to_string(),
        );
        assert_eq!(
            generic_param_names(&input).to_string(),
            quote::quote!(<'a, T>).to_string(),
        );
        assert_eq!(
            where_clause(&input).to_string(),
            quote::quote!(where 'a: 'static, T: fmt::Debug).to_string(),
        );
    }
}
