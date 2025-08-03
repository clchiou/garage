use syn::{Attribute, Path};

pub(crate) fn match_path(attr: &Attribute, segments: &[&str]) -> bool {
    match_attr_path(attr.path(), segments)
}

fn match_attr_path(path: &Path, segments: &[&str]) -> bool {
    path.is_ident(segments.last().expect("segments")) || path_eq(path, segments)
}

pub(crate) fn exact_match_path(attr: &Attribute, segments: &[&str]) -> bool {
    let path = attr.path();
    path.leading_colon.is_none() && path_eq(path, segments)
}

fn path_eq(path: &Path, segments: &[&str]) -> bool {
    path.segments
        .iter()
        .map(|segment| &segment.ident)
        .eq(segments)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_match_path() {
        fn test(path: Path, segments: &[&str], matched: bool) {
            assert_eq!(match_attr_path(&path, segments), matched);
        }

        test(syn::parse_quote!(foo), &["foo"], true);
        test(syn::parse_quote!(::foo), &["foo"], true);

        test(syn::parse_quote!(foo), &["spam", "egg", "foo"], true);
        test(syn::parse_quote!(::foo), &["spam", "egg", "foo"], false);

        test(syn::parse_quote!(foo::bar), &["foo", "bar"], true);
        test(syn::parse_quote!(::foo::bar), &["foo", "bar"], true);

        test(syn::parse_quote!(foo), &["bar"], false);
        test(syn::parse_quote!(foo), &["foo", "bar"], false);
        test(syn::parse_quote!(foo::bar), &["foo"], false);
        test(syn::parse_quote!(foo::bar), &["bar"], false);
    }
}
