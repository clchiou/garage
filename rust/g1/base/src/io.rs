use std::fmt;
use std::io::{Error, Write};

// TODO: Remove this after [#133] is fixed.
// [#133]: https://github.com/rust-lang/libs-team/issues/133
#[derive(Debug)]
pub struct Adapter<W> {
    output: W,
    error: Option<Error>,
}

impl<W> Adapter<W> {
    pub fn new(output: W) -> Self {
        Self {
            output,
            error: None,
        }
    }

    pub fn unwrap(self) -> (W, Option<Error>) {
        (self.output, self.error)
    }

    pub fn into_error(self) -> Option<Error> {
        self.error
    }
}

impl<W> fmt::Write for Adapter<W>
where
    W: Write,
{
    fn write_str(&mut self, string: &str) -> Result<(), fmt::Error> {
        self.output.write_all(string.as_bytes()).map_err(|error| {
            self.error = Some(error);
            fmt::Error
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn adapter() {
        use std::fmt::Write;

        let mut buffer = Vec::new();
        std::write!(Adapter::new(&mut buffer), "Hello, World!").unwrap();
        assert_eq!(buffer, b"Hello, World!");
    }
}
