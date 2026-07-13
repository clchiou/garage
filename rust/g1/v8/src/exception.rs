use std::cmp;
use std::error::Error;
use std::fmt::{self, Display, Formatter};
use std::sync::Arc;

/// Helper type that makes v8 exceptions easier to read.
#[derive(Clone, Debug)]
pub struct Exception {
    exception: Arc<str>,
    filename: Arc<str>,
    line: usize,
    snippet: Arc<str>,
}

impl Display for Exception {
    fn fmt(&self, f: &mut Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{}: {}:{}: {}",
            self.exception, self.filename, self.line, self.snippet,
        )
    }
}

impl Error for Exception {}

impl Exception {
    pub fn to_error<E>(try_catch: &v8::PinnedRef<'_, v8::TryCatch<v8::HandleScope>>) -> E
    where
        E: From<Self>,
    {
        Self::new(try_catch).into()
    }

    pub fn new(try_catch: &v8::PinnedRef<'_, v8::TryCatch<v8::HandleScope>>) -> Self {
        assert!(try_catch.has_caught());

        let message = try_catch.message();
        Self {
            exception: try_catch
                .exception()
                .expect("exception")
                .to_rust_string_lossy(try_catch)
                .into(),

            filename: try {
                let filename = message?.get_script_resource_name(try_catch)?;
                if filename.is_undefined() {
                    None
                } else {
                    Some(filename.to_rust_string_lossy(try_catch))
                }?
            }
            .map_or_else(|| "<unknown>".into(), Arc::from),

            line: try { message?.get_line_number(try_catch)? }.unwrap_or(0),

            snippet: try {
                extract_snippet(
                    message?
                        .get_source_line(try_catch)?
                        .to_rust_string_lossy(try_catch),
                    message?.get_start_column(),
                    message?.get_end_column(),
                )
            }
            .map_or_else(|| "...".into(), Arc::from),
        }
    }
}

fn extract_snippet(line: String, start: usize, end: usize) -> String {
    const MARGIN: usize = 20;
    let start = start.saturating_sub(MARGIN);
    let end = cmp::min(end + MARGIN, line.len());
    format!(
        "{}{}{}",
        if start == 0 { "" } else { "... " },
        line[start..end].trim(),
        if end == line.len() { "" } else { " ..." },
    )
}
