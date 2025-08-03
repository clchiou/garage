use syn::punctuated::Punctuated;
use syn::visit_mut::{self, VisitMut};
use syn::{Ident, Path};

pub(crate) struct ReplaceIdent<F>(F);

impl<F> ReplaceIdent<F> {
    pub(crate) fn new(f: F) -> Self
    where
        F: FnMut(&Ident) -> Option<Ident>,
    {
        Self(f)
    }
}

// TODO: Unfortunately, I cannot make this an associated function of `ReplaceIdent`.
pub(crate) fn ident_replacer<I, R>(
    target: &I,
    mut replacement: R,
) -> ReplaceIdent<impl FnMut(&Ident) -> Option<Ident>>
where
    I: ?Sized,
    Ident: PartialEq<I>,
    R: FnMut() -> Ident,
{
    ReplaceIdent::new(move |ident| (ident == target).then(&mut replacement))
}

impl<F> VisitMut for ReplaceIdent<F>
where
    F: FnMut(&Ident) -> Option<Ident>,
{
    fn visit_ident_mut(&mut self, ident: &mut Ident) {
        match (self.0)(ident) {
            Some(new_ident) => *ident = new_ident,
            None => visit_mut::visit_ident_mut(self, ident),
        }
    }
}

pub(crate) struct ReplacePath<F>(F);

impl<F> ReplacePath<F> {
    pub(crate) fn new(f: F) -> Self
    where
        F: FnMut(&Path) -> Option<Path>,
    {
        Self(f)
    }
}

// TODO: Unfortunately, I cannot make this an associated function of `ReplacePath`.
pub(crate) fn simple_path_replacer<I, R>(
    target: &I,
    mut replacement: R,
) -> ReplacePath<impl FnMut(&Path) -> Option<Path>>
where
    I: ?Sized,
    Ident: PartialEq<I>,
    R: FnMut() -> Path,
{
    ReplacePath::new(move |path| {
        let mut leading_colon = path.leading_colon;
        let mut segments = Punctuated::new();
        let mut replaced = false;
        for (i, segment) in path.segments.iter().enumerate() {
            if &segment.ident == target && segment.arguments.is_none() {
                let new_path = replacement();
                if i == 0 {
                    leading_colon = new_path.leading_colon;
                }
                segments.extend(new_path.segments);
                replaced = true;
            } else {
                segments.push(segment.clone());
            }
        }
        replaced.then(|| Path {
            leading_colon,
            segments,
        })
    })
}

impl<F> VisitMut for ReplacePath<F>
where
    F: FnMut(&Path) -> Option<Path>,
{
    fn visit_path_mut(&mut self, path: &mut Path) {
        match (self.0)(path) {
            Some(new_path) => *path = new_path,
            None => visit_mut::visit_path_mut(self, path),
        }
    }
}

#[cfg(test)]
mod tests {
    use syn::Expr;

    use crate::testing::i;

    use super::*;

    #[test]
    fn test_ident_replacer() {
        fn test(mut expr: Expr, expect: Expr) {
            ident_replacer("self", || i("foo")).visit_expr_mut(&mut expr);
            assert_eq!(expr, expect);
        }

        test(syn::parse_quote!(1 + 2), syn::parse_quote!(1 + 2));

        test(
            syn::parse_quote!(self.f(&mut self, x::self::y)),
            syn::parse_quote!(foo.f(&mut foo, x::foo::y)),
        );
    }

    #[test]
    fn test_simple_path_replacer() {
        fn test(mut expr: Expr, expect: Expr) {
            let path: Path = syn::parse_quote!(::foo::bar::<T>);
            simple_path_replacer("Self", || path.clone()).visit_expr_mut(&mut expr);
            assert_eq!(expr, expect);
        }

        test(syn::parse_quote!(foo::bar()), syn::parse_quote!(foo::bar()));

        test(
            syn::parse_quote!(<T as Foo>::Self::Output::f()),
            syn::parse_quote!(<T as Foo>::foo::bar::<T>::Output::f()),
        );
        test(
            syn::parse_quote!(<Self as Foo>::Self::Output::f()),
            syn::parse_quote!(<::foo::bar::<T> as Foo>::foo::bar::<T>::Output::f()),
        );

        // Not simple segment.
        test(
            syn::parse_quote!(Self::<T>::f()),
            syn::parse_quote!(Self::<T>::f()),
        );
    }
}
