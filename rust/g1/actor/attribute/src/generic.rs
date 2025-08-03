//! Finds a generic parameter in a type or a type predicate.

use syn::punctuated::Punctuated;
use syn::visit::{self, Visit};
use syn::{
    AngleBracketedGenericArguments, AssocType, Constraint, Expr, GenericArgument, Ident,
    ParenthesizedGenericArguments, Path, PathArguments, PredicateType, QSelf, ReturnType, Token,
    TraitBound, Type, TypeArray, TypeGroup, TypeImplTrait, TypeParamBound, TypeParen, TypePath,
    TypePtr, TypeReference, TypeSlice, TypeTraitObject, TypeTuple,
};

pub(super) fn type_find(type_: &Type, param: &Ident) -> bool {
    match type_ {
        Type::Array(TypeArray { elem, len, .. }) => type_find(elem, param) || expr_find(len, param),

        Type::Group(TypeGroup { elem, .. })
        | Type::Paren(TypeParen { elem, .. })
        | Type::Ptr(TypePtr { elem, .. })
        | Type::Reference(TypeReference { elem, .. })
        | Type::Slice(TypeSlice { elem, .. }) => type_find(elem, param),

        Type::Tuple(TypeTuple { elems, .. }) => elems.iter().any(|elem| type_find(elem, param)),

        Type::ImplTrait(TypeImplTrait { bounds, .. })
        | Type::TraitObject(TypeTraitObject { bounds, .. }) => bounds_find(bounds, param),

        Type::Path(TypePath { qself, path }) => {
            qself
                .as_ref()
                .is_some_and(|QSelf { ty, .. }| type_find(ty, param))
                || path_find(path, param)
        }

        _ => false,
    }
}

pub(super) fn predicate_type_find_any(predicate: &PredicateType, params: &[Ident]) -> bool {
    params
        .iter()
        .any(|param| predicate_type_find(predicate, param))
}

fn predicate_type_find(predicate: &PredicateType, param: &Ident) -> bool {
    type_find(&predicate.bounded_ty, param) || bounds_find(&predicate.bounds, param)
}

fn bounds_find(bounds: &Punctuated<TypeParamBound, Token![+]>, param: &Ident) -> bool {
    bounds.iter().any(|bound| bound_find(bound, param))
}

fn bound_find(bound: &TypeParamBound, param: &Ident) -> bool {
    match bound {
        TypeParamBound::Trait(TraitBound { path, .. }) => path_find(path, param),
        _ => false,
    }
}

fn path_find(path: &Path, param: &Ident) -> bool {
    path.is_ident(param)
        || (path.leading_colon.is_none() && &path.segments[0].ident == param)
        || path
            .segments
            .iter()
            .any(|segment| path_arguments_find(&segment.arguments, param))
}

fn path_arguments_find(arguments: &PathArguments, param: &Ident) -> bool {
    match arguments {
        PathArguments::None => false,
        PathArguments::AngleBracketed(angle) => angle_bracketed_find(angle, param),
        PathArguments::Parenthesized(parenthesized) => parenthesized_find(parenthesized, param),
    }
}

fn angle_bracketed_find(angle_bracketed: &AngleBracketedGenericArguments, param: &Ident) -> bool {
    angle_bracketed
        .args
        .iter()
        .any(|arg| generic_argument_find(arg, param))
}

fn generic_argument_find(arg: &GenericArgument, param: &Ident) -> bool {
    match arg {
        GenericArgument::Type(type_) => type_find(type_, param),

        GenericArgument::AssocType(AssocType { generics, ty, .. }) => {
            generics
                .as_ref()
                .is_some_and(|generics| angle_bracketed_find(generics, param))
                || type_find(ty, param)
        }
        GenericArgument::Constraint(Constraint {
            ident,
            generics,
            bounds,
            ..
        }) => {
            ident == param
                || generics
                    .as_ref()
                    .is_some_and(|generics| angle_bracketed_find(generics, param))
                || bounds_find(bounds, param)
        }

        _ => false,
    }
}

fn parenthesized_find(parenthesized: &ParenthesizedGenericArguments, param: &Ident) -> bool {
    parenthesized
        .inputs
        .iter()
        .any(|type_| type_find(type_, param))
        || return_type_find(&parenthesized.output, param)
}

fn return_type_find(return_: &ReturnType, param: &Ident) -> bool {
    match return_ {
        ReturnType::Default => false,
        ReturnType::Type(_, type_) => type_find(type_, param),
    }
}

fn expr_find(expr: &Expr, param: &Ident) -> bool {
    struct ExprFind<'a> {
        param: &'a Ident,
        found: bool,
    }

    impl<'ast> Visit<'ast> for ExprFind<'_> {
        fn visit_ident(&mut self, ident: &'ast Ident) {
            if ident == self.param {
                self.found = true;
            }
            visit::visit_ident(self, ident)
        }
    }

    let mut finder = ExprFind {
        param,
        found: false,
    };
    finder.visit_expr(expr);
    finder.found
}

#[cfg(test)]
mod tests {
    use quote::ToTokens;
    use syn::WherePredicate;

    use crate::testing::i;

    use super::*;

    fn test<T, F>(matcher: F, testdata: &[T])
    where
        T: PartialEq + ToTokens,
        F: Fn(&T, &Ident) -> bool,
    {
        let t = i("T");
        let u = i("U");
        for target in testdata {
            assert!(
                matcher(target, &t),
                "expect T in {}",
                quote::quote!(#target),
            );
            assert!(
                !matcher(target, &u),
                "expect U not in {}",
                quote::quote!(#target),
            );
        }
    }

    fn test_not_found<T, F>(matcher: F, testdata: &[T])
    where
        T: PartialEq + ToTokens,
        F: Fn(&T, &Ident) -> bool,
    {
        let t = i("T");
        for target in testdata {
            assert!(
                !matcher(target, &t),
                "expect T not in {}",
                quote::quote!(#target),
            );
        }
    }

    #[test]
    fn test_type_find() {
        test(
            type_find,
            &[
                // Array.
                syn::parse_quote!([T; 0]),
                syn::parse_quote!([A; T]),
                // `impl Trait`.
                syn::parse_quote!(impl T), // Invalid Rust code.  Should we reject it?
                syn::parse_quote!(impl Iterator<Item = T>),
                syn::parse_quote!(impl Fn(T)),
                syn::parse_quote!(impl Fn() -> T),
                syn::parse_quote!(impl Clone + From<T>),
                // Parenthesized.
                syn::parse_quote!((T)),
                // Path `QSelf`.
                syn::parse_quote!(<T as Iterator>::Item),
                syn::parse_quote!(<Self as T>::Item), // Invalid Rust code.  Should we reject it?
                syn::parse_quote!(<Self as Trait<T>>::Output),
                syn::parse_quote!(<Self as Iterator<Item = T>>::Item),
                syn::parse_quote!(<<T as Iterator>::Item as Iterator>::Item),
                syn::parse_quote!(<<Self as Trait<T>>::Output as Iterator>::Item),
                syn::parse_quote!(<<Self as Iterator<Item = T>>::Item as Iterator>::Item),
                // Path.
                syn::parse_quote!(T),
                syn::parse_quote!(T<A, B>), // Invalid Rust code.  Should we reject it?
                syn::parse_quote!(T::Output),
                syn::parse_quote!(T::<A, B>), // Invalid Rust code.  Should we reject it?
                syn::parse_quote!(Result<T, _>),
                syn::parse_quote!(Result::<T, _>),
                syn::parse_quote!(::A::B::<T>::C),
                // Pointer.
                syn::parse_quote!(*const T),
                syn::parse_quote!(*mut T),
                // Reference.
                syn::parse_quote!(&T),
                syn::parse_quote!(&mut T),
                // Slice.
                syn::parse_quote!([T]),
                syn::parse_quote!(&[T]),
                syn::parse_quote!(&mut [T]),
                // Trait object.
                syn::parse_quote!(dyn T), // Invalid Rust code.  Should we reject it?
                syn::parse_quote!(dyn Iterator<Item = T>),
                syn::parse_quote!(dyn Fn(T)),
                syn::parse_quote!(dyn Fn() -> T),
                syn::parse_quote!(dyn Clone + From<T>),
                // Tuple.
                syn::parse_quote!((T,)),
                syn::parse_quote!((A, B, T)),
            ],
        );
        test_not_found(
            type_find,
            &[
                // Bare function.
                syn::parse_quote!(fn(u8)),
                // Inferred type.
                syn::parse_quote!(_),
                // Macro.
                syn::parse_quote!(println!("")),
                // Never type.
                syn::parse_quote!(!),
                // Path `QSelf`.
                syn::parse_quote!(<Self as Iterator>::T),
                // Path.
                syn::parse_quote!(::T),
                syn::parse_quote!(Self::T),
                // Tuple.
                syn::parse_quote!(()),
                syn::parse_quote!((A, B)),
            ],
        );
    }

    #[test]
    fn test_predicate_type_find() {
        fn parse(predicate: WherePredicate) -> PredicateType {
            match predicate {
                WherePredicate::Type(predicate) => predicate,
                _ => unreachable!(),
            }
        }

        test(
            predicate_type_find,
            &[
                parse(syn::parse_quote!(T: Deserialize<'de>)),
                parse(syn::parse_quote!(T: 'static)),
                parse(syn::parse_quote!(Arc<T>: Clone)),
                parse(syn::parse_quote!(A: From<T>)),
                parse(syn::parse_quote!(A: Iterator<Item = T>)),
                parse(syn::parse_quote!(A: Clone + From<T>)),
                parse(syn::parse_quote!(<T as Iterator>::Item: PartialEq)),
                parse(syn::parse_quote!(<A as Iterator<Item = T>>::Item: PartialEq)),
                parse(syn::parse_quote!(for<'a> T: Iterator<Item = &'a str>)),
                parse(syn::parse_quote!(T: for<'a> Iterator<Item = &'a str>)),
            ],
        );
    }

    #[test]
    fn test_path_find() {
        test(
            path_find,
            &[
                syn::parse_quote!(T),
                syn::parse_quote!(T<A, B>), // Invalid Rust code.  Should we reject it?
                syn::parse_quote!(T::Output),
                syn::parse_quote!(T::<A, B>),
                syn::parse_quote!(Result<T, _>),
                syn::parse_quote!(Result::<T, _>),
                syn::parse_quote!(::A::B::<T>::C),
            ],
        );
        test_not_found(
            path_find,
            &[syn::parse_quote!(::T), syn::parse_quote!(Self::T)],
        );
    }

    #[test]
    fn test_angle_bracketed_find() {
        test(
            angle_bracketed_find,
            &[
                syn::parse_quote!(<T>),
                syn::parse_quote!(<A, T>),
                syn::parse_quote!(<A: From<T>>),
                syn::parse_quote!(<A: Iterator<Item = T>>),
                syn::parse_quote!(<A: Clone + From<T>>),
            ],
        );
    }

    #[test]
    fn test_generic_argument_find() {
        test(
            generic_argument_find,
            &[
                syn::parse_quote!(T),
                syn::parse_quote!(From<T>), // Invalid Rust code.  Should we reject it?
                syn::parse_quote!(Iterator<Item = T>), // Invalid Rust code.  Should we reject it?
                syn::parse_quote!(Item = T),
                syn::parse_quote!(A: T), // Invalid Rust code.  Should we reject it?
                syn::parse_quote!(A: From<T>),
                syn::parse_quote!(A: Iterator<Item = T>),
                syn::parse_quote!(A: Clone + From<T>),
            ],
        );
        test_not_found(
            generic_argument_find,
            &[
                syn::parse_quote!('static),
                syn::parse_quote!(T = Item),
                syn::parse_quote!({ 1 + 2 }),
                syn::parse_quote!(PANIC = false),
            ],
        );
    }

    #[test]
    fn test_parenthesized_find() {
        test(
            parenthesized_find,
            &[
                syn::parse_quote!(() -> T),
                syn::parse_quote!((T)),
                syn::parse_quote!((A, T) -> B),
            ],
        );
    }

    #[test]
    fn test_return_type_find() {
        test(return_type_find, &[syn::parse_quote!(-> T)]);
        test_not_found(
            return_type_find,
            &[
                syn::parse_quote!(),
                syn::parse_quote!(-> ()),
                syn::parse_quote!(-> !),
            ],
        );
    }

    #[test]
    fn test_expr_find() {
        test(
            expr_find,
            &[syn::parse_quote!(T + 1), syn::parse_quote!(f(1 + g(T)))],
        );
    }
}
