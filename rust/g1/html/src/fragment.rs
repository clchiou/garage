//! This is designed to create temporary HTML fragments that are immediately written to the output.
//! The temporary variables inside a fragment prevent it from being returned to the caller.
//!
//! NOTE: We had implemented nested fragments in an earlier version of the prototype, but
//! [temporary scopes] turned out to be more difficult to deal with, even within a single
//! expression.  We tried a few workarounds, but they were not very effective.  We concluded that
//! nested fragments added more complexity to the implementation and to the users than they were
//! worth.
//!
//! [temporary scopes]: https://doc.rust-lang.org/reference/destructors.html#temporary-scopes

use std::fmt::Display;
use std::io::{Error, Write};

use crate::FormatArgs;

#[macro_export]
macro_rules! fragment {
    ($($i:tt)*) => {
        // We move the actual work to another macro so that, when given invalid input, it does not
        // produce the obscure "recursion limit reached while expanding `fragment!`" error.
        $crate::_f!([] [ $($i)* ])
    }
}

#[macro_export]
macro_rules! _f {
    ([ $($o:expr,)* ] []) => {
        $crate::fragment::Fragment::new([$($o),*])
    };

    //
    // Start tag or void element.
    //

    ([ $($o:expr,)* ] [ <                   $t:ident      $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)*      ] [ { ::std::stringify!($t) } ; ; ] [ $($i)*    ]) };

    ([ $($o:expr,)* ] [ <                   $t:block      $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)*      ] [                     $t    ; ; ] [ $($i)*    ]) };

    // DTD.
    ([ $($o:expr,)* ] [ < !                 $t:ident      $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)*      ] [ { $crate::_f!(@dtd  $t) } ; ; ] [ $($i)*    ]) };

    //
    // Attribute name.
    //

    ([ $($o:expr,)* ] [ $t:block ; $($a:expr,)* ;                 ] [ $n:ident  $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)*      ] [ $t       ; $($a,)*      ; { ::std::stringify!($n) } ] [ $($i)*    ]) };

    ([ $($o:expr,)* ] [ $t:block ; $($a:expr,)* ;                 ] [ $n:block  $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)*      ] [ $t       ; $($a,)*      ;                     $n    ] [ $($i)*    ]) };

    //
    // Attribute value.
    //

    ([ $($o:expr,)* ] [ $t:block ; $($a:expr,)* ;            $n:block ] [ = $v:literal $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)*      ] [ $t       ; $($a,)* $crate::_f!(@attr $n,            $v), ; ] [ $($i)*    ]) };

    ([ $($o:expr,)* ] [ $t:block ; $($a:expr,)* ;            $n:block ] [ = $v:block   $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)*      ] [ $t       ; $($a,)* $crate::_f!(@attr $n,            $v), ; ] [ $($i)*    ]) };

    ([ $($o:expr,)* ] [ $t:block ; $($a:expr,)* ;            $n:block ] [              $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)*      ] [ $t       ; $($a,)* $crate::_f!(@attr $n               ), ; ] [ $($i)*    ]) };

    //
    // End of start tag or void element.
    //

    ([ $($o:expr,)* ] [           $t:block ; $($a:expr,)* ; ] [   > $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)* $crate::_f!(@start $t,        $($a),*),      ] [     $($i)*    ]) };

    ([ $($o:expr,)* ] [           $t:block ; $($a:expr,)* ; ] [ / > $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)* $crate::_f!(@void  $t,        $($a),*),      ] [     $($i)*    ]) };

    //
    // End tag.
    //

    ([ $($o:expr,)* ] [ < /     $t:ident > $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)* $crate::_f!(@end $t),   ] [ $($i)*    ]) };

    ([ $($o:expr,)* ] [ < /     $t:block > $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)* $crate::_f!(@end $t),   ] [ $($i)*    ]) };

    //
    // Raw text element.
    //
    // It is a bit confusing here: the HTML spec refers to its text element as the "raw text
    // element", but in this context, we use "raw" to mean "disable escaping".
    //
    // Somehow, Rust does not expose literal suffixes to declarative macros, so we have to specify
    // a separate identifier (in this case, `raw`).
    //

    ([ $($o:expr,)* ] [          $t:literal $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)* $crate::_f!(@text $t),   ] [ $($i)*    ]) };

    ([ $($o:expr,)* ] [          $t:block   $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)* $crate::_f!(@text $t),   ] [ $($i)*    ]) };

    ([ $($o:expr,)* ] [ raw     $t:literal $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)* $crate::_f!(@raw $t),   ] [ $($i)*    ]) };

    ([ $($o:expr,)* ] [ raw     $t:block   $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)* $crate::_f!(@raw $t),   ] [ $($i)*    ]) };

    ([ $($o:expr,)* ] [ f (        $f:literal $(, $a:expr)* $(,)? ) $($i:tt)* ]) => { $crate::_f!
    ([ $($o,)* $crate::_f!(@format $f,          $($a),*),       ] [ $($i)*    ]) };

    //
    // Helpers.
    //

    (@dtd $t:ident $(,)?) => {
        ::std::concat!("!", ::std::stringify!($t))
    };

    (@attr $n:block, $v:literal $(,)?) => {
        $crate::fragment::Attr::new($n, ::std::option::Option::Some(&$v))
    };
    (@attr $n:block, $v:block $(,)?) => {
        $crate::fragment::Attr::new($n, ::std::option::Option::Some(&$v))
    };
    (@attr $n:block $(,)?) => {
        $crate::fragment::Attr::new($n, ::std::option::Option::None)
    };

    (@start $t:block $(, $a:expr)* $(,)?) => {
        $crate::fragment::Piece::StartTag { tag: $t, attrs: &[$($a),*] }
    };

    (@void $t:block $(, $a:expr)* $(,)?) => {
        $crate::fragment::Piece::Void { tag: $t, attrs: &[$($a),*] }
    };

    (@end $t:ident $(,)?) => {
        $crate::fragment::Piece::EndTag { tag: ::std::stringify!($t) }
    };
    (@end $t:block $(,)?) => {
        $crate::fragment::Piece::EndTag { tag: $t }
    };

    (@text $t:literal $(,)?) => {
        $crate::fragment::Piece::Text { format_args: $crate::format_args!("{}", $t) }
    };
    (@text $t:block $(,)?) => {
        $crate::fragment::Piece::Text { format_args: $crate::format_args!("{}", $t) }
    };

    (@raw $t:literal $(,)?) => {
        $crate::fragment::Piece::Text { format_args: $crate::format_args!("{:r}", $t) }
    };
    (@raw $t:block $(,)?) => {
        $crate::fragment::Piece::Text { format_args: $crate::format_args!("{:r}", $t) }
    };

    (@format $f:literal $(, $a:expr)* $(,)?) => {
        $crate::fragment::Piece::Text { format_args: $crate::format_args!($f, $($a),*) }
    };
}

pub struct Fragment<'a, const N: usize>([Piece<'a>; N]);

pub enum Piece<'a> {
    StartTag { tag: &'a str, attrs: &'a [Attr<'a>] },
    EndTag { tag: &'a str },

    Void { tag: &'a str, attrs: &'a [Attr<'a>] },

    Text { format_args: FormatArgs<'a> },
}

pub struct Attr<'a> {
    name: &'a str,
    value: Option<&'a dyn Display>,
}

impl<const N: usize> From<Fragment<'_, N>> for String {
    fn from(fragment: Fragment<N>) -> Self {
        String::from_utf8(fragment.into()).expect("from_utf8")
    }
}

impl<const N: usize> From<Fragment<'_, N>> for Vec<u8> {
    fn from(fragment: Fragment<N>) -> Self {
        let mut output = Vec::new();
        fragment.write_to(&mut output).expect("write_to");
        output
    }
}

impl<'a, const N: usize> Fragment<'a, N> {
    pub fn new(pieces: [Piece<'a>; N]) -> Self {
        Self(pieces)
    }

    pub fn write_to<W>(self, mut output: W) -> Result<(), Error>
    where
        W: Write,
    {
        for piece in self.0 {
            piece.write_to(&mut output)?;
        }
        Ok(())
    }
}

impl Piece<'_> {
    fn write_to<W>(self, output: &mut W) -> Result<(), Error>
    where
        W: Write,
    {
        match self {
            Self::StartTag { tag, attrs } => {
                crate::write!(&mut *output, "<{tag}")?;
                write_attrs(output, attrs)?;
                output.write_all(b">")
            }
            Self::EndTag { tag } => crate::write!(output, "</{tag}>"),

            Self::Void { tag, attrs } => {
                crate::write!(&mut *output, "<{tag}")?;
                write_attrs(output, attrs)?;
                output.write_all(b" />")
            }

            Self::Text { format_args } => crate::write(output, format_args),
        }
    }
}

fn write_attrs<W>(output: &mut W, attrs: &[Attr]) -> Result<(), Error>
where
    W: Write,
{
    for attr in attrs {
        // I am not sure if this is a good idea, but we will use an empty string as a sentinel
        // value for conditionally omitting an attribute.
        if !attr.name.is_empty() {
            output.write_all(b" ")?;
            attr.write_to(output)?;
        }
    }
    Ok(())
}

impl<'a> Attr<'a> {
    pub fn new(name: &'a str, value: Option<&'a dyn Display>) -> Self {
        Self { name, value }
    }

    fn write_to<W>(&self, output: &mut W) -> Result<(), Error>
    where
        W: Write,
    {
        assert!(!self.name.is_empty());
        match self.value {
            Some(value) => crate::write!(output, r#"{self.name}="{value}""#),
            None => crate::write!(output, "{self.name}"),
        }
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn fragment() {
        assert_eq!(String::from(crate::fragment! {}), "");

        assert_eq!(
            String::from(crate::fragment! {
                <!doctype html>
                <{"%if"}>
                    <a href="foobar" {"data-set"}={1 + 2} enabled>
                        "The answer is: " {42}
                        <br />
                    </a>
                </{"%if"}>
            }),
            r#"<!doctype html><%if><a href="foobar" data-set="3" enabled>The answer is: 42<br /></a></%if>"#,
        );

        assert_eq!(
            String::from(crate::fragment! {
                r#"&<>"'{} -- "#
                raw r#"&<>"'{} -- "#
                { r#"&<>"'{} -- "# }
                raw { r#"&<>"'{} -- "# }
                f(r#"&<>"'{x} -- "#, x = r#"&<>"'"#)
            }),
            r#"&amp;&lt;&gt;&quot;&#x27;{} -- &<>"'{} -- &amp;&lt;&gt;&quot;&#x27;{} -- &<>"'{} -- &<>"'&amp;&lt;&gt;&quot;&#x27; -- "#,
        );

        assert_eq!(String::from(crate::fragment!(<a {""}="true">)), r#"<a>"#);
        assert_eq!(String::from(crate::fragment!(<a {""}>)), r#"<a>"#);
        assert_eq!(
            String::from(crate::fragment!(<a href="foobar" {""}="true" enabled>)),
            r#"<a href="foobar" enabled>"#,
        );
        assert_eq!(
            String::from(crate::fragment!(<a href="foobar" {""} enabled>)),
            r#"<a href="foobar" enabled>"#,
        );
    }
}
