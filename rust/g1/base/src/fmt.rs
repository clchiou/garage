use std::fmt;
use std::io;
use std::str::{self, MatchIndices};
use std::sync::Arc;

pub use g1_base_derive::DebugExt;

pub fn format(format: &str, args: &[&dyn fmt::Display]) -> String {
    let mut output = String::new();
    write(&mut output, format, args).expect("g1_base::fmt::format");
    output
}

#[macro_export]
macro_rules! format_str {
    ($buffer:expr $(, $($arg:tt)*)?) => {{
        use ::std::fmt::Write as _;
        let mut writer = $crate::fmt::StrWriter::new($buffer);
        writer.write_fmt(::std::format_args!($($($arg)*)?)).expect("g1_base::fmt::format_str!");
        writer.into_str()
    }};
}

pub fn format_str<'a>(buffer: &'a mut [u8], format: &str, args: &[&dyn fmt::Display]) -> &'a str {
    let mut writer = StrWriter::new(buffer);
    write(&mut writer, format, args).expect("g1_base::fmt::format_str");
    writer.into_str()
}

pub fn write<W: fmt::Write>(
    writer: &mut W,
    format: &str,
    args: &[&dyn fmt::Display],
) -> Result<(), fmt::Error> {
    let mut parser = FormatParser::new(format);
    // Do not use `Iterator::zip`, as it incorrectly consumes one additional item from either
    // `parser` or `args` at the end.
    writer.write_str(parser.next().ok_or(fmt::Error)??)?;
    for arg in args {
        writer.write_fmt(std::format_args!("{arg}"))?;
        writer.write_str(parser.next().ok_or(fmt::Error)??)?;
    }
    if parser.next().is_none() {
        Ok(())
    } else {
        Err(fmt::Error)
    }
}

struct FormatParser<'a> {
    format: &'a str,
    i: usize,
    braces: MatchIndices<'a, [char; 2]>,
}

impl<'a> FormatParser<'a> {
    fn new(format: &'a str) -> Self {
        Self {
            format,
            i: 0,
            braces: format.match_indices(['{', '}']),
        }
    }
}

impl<'a> Iterator for FormatParser<'a> {
    type Item = Result<&'a str, fmt::Error>;

    fn next(&mut self) -> Option<Self::Item> {
        if self.i > self.format.len() {
            return None;
        }

        while let Some((j, brace)) = self.braces.next() {
            match (brace, self.braces.next()) {
                ("{", Some((k, "{"))) | ("}", Some((k, "}"))) if j + 1 == k => {}
                ("{", Some((k, "}"))) if self.format[j + 1..k].chars().all(char::is_whitespace) => {
                    let piece = &self.format[self.i..j];
                    self.i = k + 1;
                    return Some(Ok(piece));
                }
                _ => {
                    self.i = self.format.len() + 1;
                    return Some(Err(fmt::Error));
                }
            }
        }

        let piece = &self.format[self.i..];
        self.i = self.format.len() + 1;
        Some(Ok(piece))
    }
}

#[derive(Debug)]
pub struct StrWriter<'a> {
    buffer: &'a mut [u8],
    offset: usize,
}

impl<'a> StrWriter<'a> {
    pub fn new(buffer: &'a mut [u8]) -> Self {
        Self { buffer, offset: 0 }
    }

    pub fn as_str(&self) -> &str {
        unsafe { str::from_utf8_unchecked(&self.buffer[..self.offset]) }
    }

    pub fn into_str(self) -> &'a str {
        unsafe { str::from_utf8_unchecked(&self.buffer[..self.offset]) }
    }
}

impl fmt::Write for StrWriter<'_> {
    fn write_str(&mut self, string: &str) -> Result<(), fmt::Error> {
        let slice = string.as_bytes();
        self.buffer
            .get_mut(self.offset..self.offset + slice.len())
            .ok_or(fmt::Error)?
            .copy_from_slice(slice);
        self.offset += slice.len();
        Ok(())
    }
}

// TODO: Remove this after [#133] is fixed.
// [#133]: https://github.com/rust-lang/libs-team/issues/133
#[derive(Debug)]
pub struct Adapter<W> {
    output: W,
    error: Option<io::Error>,
}

impl<W> Adapter<W> {
    pub fn new(output: W) -> Self {
        Self {
            output,
            error: None,
        }
    }

    pub fn unwrap(self) -> (W, Option<io::Error>) {
        (self.output, self.error)
    }

    pub fn into_error(self) -> Option<io::Error> {
        self.error
    }
}

impl<W> fmt::Write for Adapter<W>
where
    W: io::Write,
{
    fn write_str(&mut self, string: &str) -> Result<(), fmt::Error> {
        self.output.write_all(string.as_bytes()).map_err(|error| {
            self.error = Some(error);
            fmt::Error
        })
    }
}

/// Escapes non-ASCII characters in a slice to produce `fmt::Debug` output.
pub struct EscapeAscii<'a, T: ?Sized = [u8]>(pub &'a T);

// TODO: Make `EscapeAscii` support `&Some(&[T; N])` and `&Some(&&[T])`.
impl<'a, T> fmt::Debug for EscapeAscii<'a, Option<T>>
where
    EscapeAscii<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.0 {
            Some(some) => f.debug_tuple("Some").field(&EscapeAscii(some)).finish(),
            None => write!(f, "None"),
        }
    }
}

impl<'a, T> fmt::Debug for EscapeAscii<'a, Arc<T>>
where
    EscapeAscii<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        EscapeAscii(&**self.0).fmt(f)
    }
}

// TODO: I do not know why, but `impl for EscapeAscii<'a, Arc<T>>` does not seem to cover this
// case.
impl<'a, T> fmt::Debug for EscapeAscii<'a, Arc<[T]>>
where
    EscapeAscii<'a, [T]>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        EscapeAscii(&**self.0).fmt(f)
    }
}

// TODO: Make `EscapeAscii` support `&[&[T; N]]` and `&[&&[T]]`.
impl<'a, T> fmt::Debug for EscapeAscii<'a, Vec<T>>
where
    EscapeAscii<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        EscapeAscii(self.0.as_slice()).fmt(f)
    }
}

impl<'a, T, const N: usize> fmt::Debug for EscapeAscii<'a, [T; N]>
where
    EscapeAscii<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        EscapeAscii(self.0.as_slice()).fmt(f)
    }
}

impl<'a, T> fmt::Debug for EscapeAscii<'a, &[T]>
where
    EscapeAscii<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        EscapeAscii(*self.0).fmt(f)
    }
}

impl<'a, T> fmt::Debug for EscapeAscii<'a, [T]>
where
    EscapeAscii<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_list()
            .entries(self.0.iter().map(EscapeAscii))
            .finish()
    }
}

impl<const N: usize> fmt::Debug for EscapeAscii<'_, [u8; N]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        EscapeAscii(self.0.as_slice()).fmt(f)
    }
}

impl fmt::Debug for EscapeAscii<'_, &[u8]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        EscapeAscii(*self.0).fmt(f)
    }
}

impl fmt::Debug for EscapeAscii<'_, [u8]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "\"{}\"", self.0.escape_ascii())
    }
}

/// Formats a bytes slice into a hex string.
pub struct Hex<'a, T: ?Sized = [u8]>(pub &'a T);

// TODO: Make `Hex` support `&Some(&[T; N])` and `&Some(&&[T])`.
impl<'a, T> fmt::Debug for Hex<'a, Option<T>>
where
    Hex<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.0 {
            Some(some) => f.debug_tuple("Some").field(&Hex(some)).finish(),
            None => write!(f, "None"),
        }
    }
}

impl<'a, T> fmt::Debug for Hex<'a, Arc<T>>
where
    Hex<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        Hex(&**self.0).fmt(f)
    }
}

// TODO: I do not know why, but `impl for Hex<'a, Arc<T>>` does not seem to cover this case.
impl<'a, T> fmt::Debug for Hex<'a, Arc<[T]>>
where
    Hex<'a, [T]>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        Hex(&**self.0).fmt(f)
    }
}

// TODO: Make `Hex` support `&[&[T; N]]` and `&[&&[T]]`.
impl<'a, T> fmt::Debug for Hex<'a, Vec<T>>
where
    Hex<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        Hex(self.0.as_slice()).fmt(f)
    }
}

impl<'a, T, const N: usize> fmt::Debug for Hex<'a, [T; N]>
where
    Hex<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        Hex(self.0.as_slice()).fmt(f)
    }
}

impl<'a, T> fmt::Debug for Hex<'a, &[T]>
where
    Hex<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        Hex(*self.0).fmt(f)
    }
}

impl<'a, T> fmt::Debug for Hex<'a, [T]>
where
    Hex<'a, T>: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_list().entries(self.0.iter().map(Hex)).finish()
    }
}

impl<const N: usize> fmt::Debug for Hex<'_, [u8; N]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        Hex(self.0.as_slice()).fmt(f)
    }
}

impl fmt::Debug for Hex<'_, &[u8]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        Hex(*self.0).fmt(f)
    }
}

impl fmt::Debug for Hex<'_, [u8]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        for byte in self.0 {
            write!(f, "{byte:02x}")?;
        }
        Ok(())
    }
}

/// Recursively inserts placeholders for a value of a type that does not "fully" implement
/// `std::fmt::Debug`.
pub struct InsertPlaceholder<'a, T: ?Sized>(pub &'a T);

/// Inserts a placeholder for a value of a type that does not implement `std::fmt::Debug`.
struct InsertPlaceholderBase<T>(pub T);

impl<T> fmt::Debug for InsertPlaceholder<'_, Option<T>> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.0 {
            Some(some) => f
                .debug_tuple("Some")
                .field(&InsertPlaceholder(some))
                .finish(),
            None => write!(f, "None"),
        }
    }
}

impl<T, E> fmt::Debug for InsertPlaceholder<'_, Result<T, E>> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.0 {
            Ok(ok) => f.debug_tuple("Ok").field(&InsertPlaceholder(ok)).finish(),
            Err(err) => f.debug_tuple("Err").field(&InsertPlaceholder(err)).finish(),
        }
    }
}

macro_rules! generate_tuple {
    ($($name:ident),* $(,)?) => {
        generate_tuple!(@loop ; $($name)*);
    };

    (@loop $($name:ident)* ; $head:ident $($tail:ident)*) => {
        generate_tuple!(@gen $($name)*);
        generate_tuple!(@loop $($name)* $head ; $($tail)*);
    };
    (@loop $($name:ident)* ; ) => {
        generate_tuple!(@gen $($name)*);
    };

    (@gen $($name:ident)+) => {
        impl<'a, $($name),+> fmt::Debug for InsertPlaceholder<'a, ($($name,)+)> {
            #[allow(non_snake_case)]
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                let mut builder = f.debug_tuple("");
                let ($($name,)+) = &self.0;
                $(builder.field(&InsertPlaceholder($name));)+
                builder.finish()
            }
        }
    };
    (@gen) => {};
}

generate_tuple!(T0, T1, T2, T3, T4, T5, T6, T7, T8, T9, T10, T11);

impl<T> fmt::Debug for InsertPlaceholder<'_, Vec<T>> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        InsertPlaceholder(self.0.as_slice()).fmt(f)
    }
}

impl<T, const N: usize> fmt::Debug for InsertPlaceholder<'_, [T; N]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        InsertPlaceholder(self.0.as_slice()).fmt(f)
    }
}

impl<'a, T> fmt::Debug for InsertPlaceholder<'a, &'a [T]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        InsertPlaceholder(*self.0).fmt(f)
    }
}

impl<T> fmt::Debug for InsertPlaceholder<'_, [T]> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_list()
            .entries(self.0.iter().map(InsertPlaceholder))
            .finish()
    }
}

impl<T> fmt::Debug for InsertPlaceholder<'_, T> {
    default fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        InsertPlaceholderBase(&self.0).fmt(f)
    }
}

#[rustc_unsafe_specialization_marker]
trait HaveImplDebug: fmt::Debug {}

impl<T: fmt::Debug> HaveImplDebug for T {}

impl<T> fmt::Debug for InsertPlaceholderBase<T> {
    default fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "_")
    }
}

impl<T: HaveImplDebug> fmt::Debug for InsertPlaceholderBase<T> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(f)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_format() {
        assert_eq!(format("你好，{}！", &[&"世界"]), "你好，世界！");
        assert_eq!(format("Hello, {}!", &[&"World"]), "Hello, World!");

        let buffer = &mut [0u8; 32];

        assert_eq!(
            crate::format_str!(buffer, "你好，{}！", "世界"),
            "你好，世界！",
        );
        assert_eq!(
            crate::format_str!(buffer, "Hello, {}!", "World"),
            "Hello, World!",
        );

        assert_eq!(format_str(buffer, "你好，{}！", &[&"世界"]), "你好，世界！");
        assert_eq!(
            format_str(buffer, "Hello, {}!", &[&"World"]),
            "Hello, World!",
        );
    }

    #[test]
    fn test_write() {
        fn test(format: &str, args: &[&dyn fmt::Display], expect: Result<&str, fmt::Error>) {
            let mut output = String::new();
            assert_eq!(write(&mut output, format, args).map(|()| &*output), expect);
        }

        test("", &[], Ok(""));
        test("Hello, {}!", &[&"World"], Ok("Hello, World!"));
        test("The answer is {}.", &[&42], Ok("The answer is 42."));
        test("{ \t\r\n} \t\r\n", &[&"x"], Ok("x \t\r\n"));
        test("{{ \t\r\n}} \t\r\n", &[], Ok("{{ \t\r\n}} \t\r\n"));

        test("{ {", &[], Err(fmt::Error));
        test("} }", &[], Err(fmt::Error));
        test("{x}", &[], Err(fmt::Error));

        test("{}", &[], Err(fmt::Error));
        test("{}{}", &[&0], Err(fmt::Error));

        test("{}", &[&0, &"extra-arg"], Err(fmt::Error));
        test("{}{}", &[&0, &1, &"extra-arg"], Err(fmt::Error));
    }

    #[test]
    fn format_parser() {
        fn test(format: &str, expect: &[Result<&str, fmt::Error>]) {
            assert_eq!(FormatParser::new(format).collect::<Vec<_>>(), expect);
        }

        test("", &[Ok("")]);
        test("a", &[Ok("a")]);
        test("Hello, {}!", &[Ok("Hello, "), Ok("!")]);

        test("{}", &[Ok(""), Ok("")]);
        test("a{}", &[Ok("a"), Ok("")]);
        test("{}b", &[Ok(""), Ok("b")]);
        test("a{}b", &[Ok("a"), Ok("b")]);

        test("{}{}{}", &[Ok(""), Ok(""), Ok(""), Ok("")]);
        test("a{}b{}c{}d", &[Ok("a"), Ok("b"), Ok("c"), Ok("d")]);

        test("{{}}", &[Ok("{{}}")]);
        test("{{{{", &[Ok("{{{{")]);
        test("}}}}", &[Ok("}}}}")]);
        test("{{  }}", &[Ok("{{  }}")]);
        test("{{{  }}}", &[Ok("{{"), Ok("}}")]);

        test("a{ \t\r\n\u{A0}}b", &[Ok("a"), Ok("b")]);

        test("{", &[Err(fmt::Error)]);
        test("a{", &[Err(fmt::Error)]);
        test("{ {", &[Err(fmt::Error)]);
        test("a{ {", &[Err(fmt::Error)]);

        test("}", &[Err(fmt::Error)]);
        test("a}", &[Err(fmt::Error)]);
        test("} }", &[Err(fmt::Error)]);
        test("a} }", &[Err(fmt::Error)]);

        test("{x}", &[Err(fmt::Error)]);
    }

    #[test]
    fn str_writer() {
        use std::fmt::Write;

        {
            let writer = &mut [0u8; 32];
            let mut writer = StrWriter::new(writer);
            assert_eq!(writer.as_str(), "");

            std::write!(&mut writer, "你好，{}！", "世界").unwrap();
            assert_eq!(writer.as_str(), "你好，世界！");

            std::write!(&mut writer, "Hello, {}!", "World").unwrap();
            assert_eq!(writer.into_str(), "你好，世界！Hello, World!");
        }

        {
            let writer = &mut [0u8; 4];
            let mut writer = StrWriter::new(writer);
            assert_eq!(writer.as_str(), "");

            std::write!(&mut writer, "abc").unwrap();
            assert_eq!(writer.as_str(), "abc");

            assert_eq!(std::write!(&mut writer, "defg"), Err(fmt::Error));
            assert_eq!(writer.into_str(), "abc");
        }
    }

    #[test]
    fn adapter() {
        use std::fmt::Write as _;

        let mut buffer = Vec::new();
        std::write!(Adapter::new(&mut buffer), "Hello, World!").unwrap();
        assert_eq!(buffer, b"Hello, World!");
    }

    #[test]
    fn escape_ascii() {
        // TODO: Turn this into a generic function.
        macro_rules! test {
            ($data:expr, $expect:expr $(,)?) => {
                assert_eq!(format!("{:?}", EscapeAscii($data)), $expect);
            };
        }

        test!(b"spam \tegg\r\n", "\"spam \\tegg\\r\\n\"");

        let array: [u8; 8] = *b"deadbeef";
        let slice = array.as_slice();

        test!(&Some(slice), "Some(\"deadbeef\")");
        test!(&Some(Some(slice)), "Some(Some(\"deadbeef\"))");
        test!(&None as &Option<&[u8]>, "None");
        test!(&None as &Option<Option<&[u8]>>, "None");

        let arc: Arc<[u8; 8]> = Arc::new(array.clone());
        test!(&arc, "\"deadbeef\"");
        test!(&Some(arc.clone()), "Some(\"deadbeef\")");
        let arc: Arc<[u8]> = Arc::from(slice);
        test!(&arc, "\"deadbeef\"");
        test!(&Some(arc.clone()), "Some(\"deadbeef\")");
        test!(&Arc::new(Some(slice)), "Some(\"deadbeef\")");

        test!(&vec![slice], "[\"deadbeef\"]");
        test!(&vec![Some(slice), None], "[Some(\"deadbeef\"), None]");
        test!(&[slice], "[\"deadbeef\"]");
        test!([slice].as_slice(), "[\"deadbeef\"]");
        test!(&[slice].as_slice(), "[\"deadbeef\"]");

        test!(&array, "\"deadbeef\"");
        test!(slice, "\"deadbeef\"");
        test!(&slice, "\"deadbeef\"");
    }

    #[test]
    fn hex() {
        // TODO: Turn this into a generic function.
        macro_rules! test {
            ($data:expr, $expect:expr $(,)?) => {
                assert_eq!(format!("{:?}", Hex($data)), $expect);
            };
        }

        let array = [0xdeu8, 0xad, 0xbe, 0xef];
        let slice = array.as_slice();

        test!(&Some(slice), "Some(deadbeef)");
        test!(&Some(Some(slice)), "Some(Some(deadbeef))");
        test!(&None as &Option<&[u8]>, "None");
        test!(&None as &Option<Option<&[u8]>>, "None");

        let arc: Arc<[u8; 4]> = Arc::new(array.clone());
        test!(&arc, "deadbeef");
        test!(&Some(arc.clone()), "Some(deadbeef)");
        let arc: Arc<[u8]> = Arc::from(slice);
        test!(&arc, "deadbeef");
        test!(&Some(arc.clone()), "Some(deadbeef)");
        test!(&Arc::new(Some(slice)), "Some(deadbeef)");

        test!(&vec![slice], "[deadbeef]");
        test!(&vec![Some(slice), None], "[Some(deadbeef), None]");
        test!(&[slice], "[deadbeef]");
        test!([slice].as_slice(), "[deadbeef]");
        test!(&[slice].as_slice(), "[deadbeef]");

        test!(&array, "deadbeef");
        test!(slice, "deadbeef");
        test!(&slice, "deadbeef");
    }

    #[derive(Debug)]
    struct YesDebug;

    struct NoDebug;

    #[test]
    fn insert_placeholder() {
        fn test<T>(value: T, expect: &str) {
            assert_eq!(format!("{:?}", InsertPlaceholder(&value)), expect);
        }

        test(42, "42");
        test(YesDebug, "YesDebug");
        test(NoDebug, "_");
        test(insert_placeholder, "_");

        test(Some(YesDebug), "Some(YesDebug)");
        test(Some(Some(YesDebug)), "Some(Some(YesDebug))");
        test::<Option<YesDebug>>(None, "None");
        test::<Option<Option<YesDebug>>>(None, "None");

        test(Some(NoDebug), "Some(_)");
        test(Some(Some(NoDebug)), "Some(Some(_))");
        test::<Option<NoDebug>>(None, "None");
        test::<Option<Option<NoDebug>>>(None, "None");

        test::<Result<YesDebug, NoDebug>>(Ok(YesDebug), "Ok(YesDebug)");
        test::<Result<Result<YesDebug, NoDebug>, NoDebug>>(Ok(Ok(YesDebug)), "Ok(Ok(YesDebug))");
        test::<Result<YesDebug, NoDebug>>(Err(NoDebug), "Err(_)");
        test::<Result<YesDebug, Result<YesDebug, NoDebug>>>(Err(Err(NoDebug)), "Err(Err(_))");

        test((), "()");
        test((YesDebug, NoDebug), "(YesDebug, _)");
        test((YesDebug, (YesDebug, NoDebug)), "(YesDebug, (YesDebug, _))");
        test(
            (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),
            "(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)",
        );

        test(vec![YesDebug], "[YesDebug]");
        test(vec![Ok(YesDebug), Err(NoDebug)], "[Ok(YesDebug), Err(_)]");

        test([YesDebug], "[YesDebug]");
        test([Ok(YesDebug), Err(NoDebug)], "[Ok(YesDebug), Err(_)]");

        test([YesDebug].as_slice(), "[YesDebug]");
        test(
            [Ok(YesDebug), Err(NoDebug)].as_slice(),
            "[Ok(YesDebug), Err(_)]",
        );
    }

    #[test]
    fn insert_placeholder_base() {
        fn test<T>(value: T, expect: &str) {
            assert_eq!(format!("{:?}", InsertPlaceholderBase(&value)), expect);
            assert_eq!(format!("{:?}", InsertPlaceholderBase(value)), expect);
        }

        test(42, "42");
        test(YesDebug, "YesDebug");
        test(NoDebug, "_");
        test(insert_placeholder_base, "_");

        test(Some(YesDebug), "Some(YesDebug)");
        test::<Option<YesDebug>>(None, "None");

        test(Some(NoDebug), "_");
        test::<Option<NoDebug>>(None, "_");

        test::<Result<YesDebug, NoDebug>>(Ok(YesDebug), "_");
        test::<Result<YesDebug, NoDebug>>(Err(NoDebug), "_");

        test((), "()");
        test((YesDebug, NoDebug), "_");
        test((YesDebug, (YesDebug, NoDebug)), "_");
        test(
            (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),
            "(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)",
        );

        test(vec![YesDebug], "[YesDebug]");
        test(vec![Ok(YesDebug), Err(NoDebug)], "_");

        test([YesDebug], "[YesDebug]");
        test([Ok(YesDebug), Err(NoDebug)], "_");

        test([YesDebug].as_slice(), "[YesDebug]");
        test([Ok(YesDebug), Err(NoDebug)].as_slice(), "_");
    }
}
