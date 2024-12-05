mod escape;

use std::fmt::{Display, Write as _};
use std::io::{Error, Write};
use std::iter;

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

pub fn format(format_args: FormatArgs) -> Vec<u8> {
    // I do not know which capacity we should use; I just arbitrarily choose one.
    let literal_size: usize = format_args.literals.iter().copied().map(str::len).sum();
    let estimated_arg_size = format_args.args.len() * 32;
    let mut buffer = Vec::with_capacity(literal_size + estimated_arg_size);
    write(&mut buffer, format_args).expect("format");
    buffer
}

pub fn write<W>(mut output: W, format_args: FormatArgs) -> Result<(), Error>
where
    W: Write,
{
    for (literal, (arg, spec)) in iter::zip(format_args.literals, format_args.args) {
        output.write_all(literal.as_bytes())?;
        match spec {
            FormatSpec::None => {
                let mut escaper = escape::Escaper::new(&mut output);
                std::write!(escaper, "{}", arg)
                    .map_err(|error| escaper.into_error().unwrap_or_else(|| Error::other(error)))?;
            }
            FormatSpec::Raw => {
                std::write!(output, "{}", arg)?;
            }
        }
    }
    if format_args.literals.len() > format_args.args.len() {
        output.write_all(format_args.literals[format_args.literals.len() - 1].as_bytes())?;
    }
    Ok(())
}