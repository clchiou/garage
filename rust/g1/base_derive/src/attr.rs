use syn::{punctuated::Punctuated, token::Comma, Error, Expr, Field, Path};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum AttrArgType {
    AssignPath,
    Flag,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) enum AttrArgValue {
    AssignPath(Path),
    Flag,
}

impl AttrArgValue {
    pub(crate) fn into_assignee_path(self) -> Path {
        match self {
            AttrArgValue::AssignPath(path) => path,
            _ => std::panic!("expect AssignPath: {:?}", self),
        }
    }
}

pub(crate) fn parse_field_attr_args<'a, const N: usize>(
    field: &Field,
    attr_name: &str,
    attr_arg_signatures: &[(&str, AttrArgType); N],
    attr_arg_values: &'a mut [Option<AttrArgValue>; N],
) -> Result<&'a [Option<AttrArgValue>; N], Error> {
    for attr in field.attrs.iter() {
        if !attr.path().is_ident(attr_name) {
            continue;
        }
        let attr_args = attr.parse_args_with(Punctuated::<Expr, Comma>::parse_terminated)?;
        if attr_args.is_empty() {
            return Err(error::empty(attr_name));
        }
        let mut found = false;
        for attr_arg in attr_args.iter() {
            for i in 0..N {
                let (attr_arg_name, attr_arg_type) = attr_arg_signatures[i];
                let parse = match attr_arg_type {
                    AttrArgType::AssignPath => parse_attr_assign_path,
                    AttrArgType::Flag => parse_attr_flag,
                };
                if parse(attr_arg, attr_name, attr_arg_name, &mut attr_arg_values[i])? {
                    found = true;
                    break;
                }
            }
        }
        if !found {
            return Err(error::unknown(attr_name, attr));
        }
    }
    Ok(attr_arg_values)
}

fn parse_attr_assign_path(
    attr_arg: &Expr,
    attr_name: &str,
    attr_arg_name: &str,
    attr_arg_value: &mut Option<AttrArgValue>,
) -> Result<bool, Error> {
    if let Expr::Assign(assign) = attr_arg {
        if let Expr::Path(path) = assign.left.as_ref() {
            if path.path.is_ident(attr_arg_name) {
                if attr_arg_value.is_some() {
                    return Err(error::duplicated(attr_name, attr_arg_name));
                }
                if let Expr::Path(path) = assign.right.as_ref() {
                    *attr_arg_value = Some(AttrArgValue::AssignPath(path.path.clone()));
                    return Ok(true);
                }
            }
        }
    }
    Ok(false)
}

fn parse_attr_flag(
    attr_arg: &Expr,
    attr_name: &str,
    attr_arg_name: &str,
    attr_arg_value: &mut Option<AttrArgValue>,
) -> Result<bool, Error> {
    if let Expr::Path(path) = attr_arg {
        if path.path.is_ident(attr_arg_name) {
            if attr_arg_value.is_some() {
                return Err(error::duplicated(attr_name, attr_arg_name));
            }
            *attr_arg_value = Some(AttrArgValue::Flag);
            return Ok(true);
        }
    }
    Ok(false)
}

mod error {
    use syn::{Attribute, Error};

    pub(super) fn duplicated(attr_name: &str, attr_arg_name: &str) -> Error {
        crate::new_error(format!(
            "duplicated argument of `#[{}(...)]`: {}",
            attr_name, attr_arg_name,
        ))
    }

    pub(super) fn empty(attr_name: &str) -> Error {
        crate::new_error(format!(
            "`#[{}(...)]` requires non-empty arguments",
            attr_name,
        ))
    }

    pub(super) fn unknown(attr_name: &str, attr: &Attribute) -> Error {
        crate::new_error(format!(
            "unknown argument of `#[{}(...)]`: {}",
            attr_name,
            quote::quote!(#attr).to_string(),
        ))
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use syn::FieldsUnnamed;

    use super::*;

    #[test]
    fn parse() {
        let attr_arg_signatures = [
            ("bar", AttrArgType::Flag),
            ("spam", AttrArgType::AssignPath),
        ];
        let fields: FieldsUnnamed = syn::parse_quote!((
            (),
            #[foo(bar)]
            (),
            #[foo(spam = egg)]
            (),
            #[foo(bar, spam = egg)]
            (),
        ));
        let fields = fields.unnamed;
        assert_matches!(
            parse_field_attr_args(&fields[0], "foo", &attr_arg_signatures, &mut [None, None]),
            Ok(&[None, None]),
        );
        assert_matches!(
            parse_field_attr_args(&fields[1], "foo", &attr_arg_signatures, &mut [None, None]),
            Ok(&[Some(AttrArgValue::Flag), None]),
        );
        assert_matches!(
            parse_field_attr_args(&fields[2], "foo", &attr_arg_signatures, &mut [None, None]),
            Ok(&[None, Some(AttrArgValue::AssignPath(ref path))]) if path.is_ident("egg"),
        );
        assert_matches!(
            parse_field_attr_args(&fields[3], "foo", &attr_arg_signatures, &mut [None, None]),
            Ok(&[Some(AttrArgValue::Flag), Some(AttrArgValue::AssignPath(ref path))])
                if path.is_ident("egg"),
        );

        let fields: FieldsUnnamed = syn::parse_quote!((
            #[foo(bar)]
            #[foo(bar)]
            (),
            #[foo(spam = p, spam = q, )]
            (),
            #[foo()]
            (),
            #[foo(1)]
            (),
            #[foo(baz)]
            (),
        ));
        let fields = fields.unnamed;
        assert_matches!(
            parse_field_attr_args(&fields[0], "foo", &attr_arg_signatures, &mut [None, None]),
            Err(e) if e.to_string() == error::duplicated("foo", "bar").to_string(),
        );
        assert_matches!(
            parse_field_attr_args(&fields[1], "foo", &attr_arg_signatures, &mut [None, None]),
            Err(e) if e.to_string() == error::duplicated("foo", "spam").to_string(),
        );
        assert_matches!(
            parse_field_attr_args(&fields[2], "foo", &attr_arg_signatures, &mut [None, None]),
            Err(e) if e.to_string() == error::empty("foo").to_string(),
        );

        assert_matches!(
            parse_field_attr_args(&fields[3], "foo", &attr_arg_signatures, &mut [None, None]),
            Err(e) if e.to_string() == error::unknown("foo", &fields[3].attrs[0]).to_string(),
        );
        assert_matches!(
            parse_field_attr_args(&fields[4], "foo", &attr_arg_signatures, &mut [None, None]),
            Err(e) if e.to_string() == error::unknown("foo", &fields[4].attrs[0]).to_string(),
        );
    }
}
