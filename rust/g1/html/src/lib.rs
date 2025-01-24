extern crate self as g1_html;

pub mod fragment;

mod escape;
mod fragment_ext;

use std::fmt::{Display, Error, Write};
use std::iter;

use crate::escape::Escaper;

pub use g1_html_macros::{format, format_args, write};

pub struct FormatArgs<'a> {
    literals: &'a [&'static str],
    // For now, we just use `std::fmt::Display`, which makes things much easier.
    args: &'a [(&'a dyn Display, FormatSpec)],
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FormatSpec {
    None,
    Raw,
}

impl<'a> FormatArgs<'a> {
    pub const fn new(
        literals: &'a [&'static str],
        args: &'a [(&'a dyn Display, FormatSpec)],
    ) -> Self {
        Self { literals, args }
    }
}

pub fn format(format_args: FormatArgs) -> String {
    // I do not know which capacity we should use; I just arbitrarily choose one.
    let literal_size: usize = format_args.literals.iter().copied().map(str::len).sum();
    let estimated_arg_size = format_args.args.len() * 32;
    let mut buffer = String::with_capacity(literal_size + estimated_arg_size);
    write(&mut buffer, format_args).expect("format");
    buffer
}

pub fn write<W>(mut output: W, format_args: FormatArgs) -> Result<(), Error>
where
    W: Write,
{
    for (literal, (arg, spec)) in iter::zip(format_args.literals, format_args.args) {
        output.write_str(literal)?;
        match spec {
            FormatSpec::None => std::write!(Escaper::new(&mut output), "{}", arg)?,
            FormatSpec::Raw => std::write!(output, "{}", arg)?,
        }
    }
    if format_args.literals.len() > format_args.args.len() {
        output.write_str(format_args.literals[format_args.literals.len() - 1])?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    #[test]
    fn write() {
        let mut output = String::new();
        crate::write!(&mut output, r#"&<>"'{}"#, r#"&<>"'"#).unwrap();
        assert_eq!(output, r#"&<>"'&amp;&lt;&gt;&quot;&#x27;"#);

        let mut output = String::new();
        crate::write!(&mut output, r#"&<>"'{:r}"#, r#"&<>"'"#).unwrap();
        assert_eq!(output, r#"&<>"'&<>"'"#);
    }
}
