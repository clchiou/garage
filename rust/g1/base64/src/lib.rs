use std::cmp;
use std::fmt;
use std::io;
use std::str;

use base64::Engine as _;
use base64::engine::general_purpose::STANDARD;

pub struct Writer<W: io::Write>(WriterImpl<W>);

impl<W: io::Write> Writer<W> {
    pub fn new(writer: W) -> Self {
        Self(WriterImpl::new(writer))
    }

    pub fn close(mut self) -> Result<(), io::Error> {
        self.0.close()
    }
}

impl<W: io::Write> io::Write for Writer<W> {
    fn write(&mut self, plaintext: &[u8]) -> Result<usize, io::Error> {
        self.0.write(plaintext)
    }

    fn flush(&mut self) -> Result<(), io::Error> {
        self.0.writer.flush()
    }
}

pub struct Display<T>(pub T);

impl<T: fmt::Display> fmt::Display for Display<T> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        use std::fmt::Write;

        struct Adapter<'a, 'b>(WriterImpl<Formatter<'a, 'b>>);

        impl Write for Adapter<'_, '_> {
            fn write_str(&mut self, string: &str) -> Result<(), fmt::Error> {
                assert_eq!(self.0.write(string.as_bytes())?, string.len());
                Ok(())
            }
        }

        std::write!(Adapter(WriterImpl::new(Formatter(f))), "{}", self.0)
    }
}

pub struct DisplayBytes<'a>(pub &'a [u8]);

impl fmt::Display for DisplayBytes<'_> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        assert_eq!(WriterImpl::new(Formatter(f)).write(self.0)?, self.0.len());
        Ok(())
    }
}

struct WriterImpl<W: Write> {
    writer: W,
    residual: [u8; 3],
    size: usize,
}

impl<W: Write> Drop for WriterImpl<W> {
    fn drop(&mut self) {
        self.close().expect("Writer::close");
    }
}

trait Write {
    type Error: fmt::Debug;

    fn write(&mut self, data: &[u8]) -> Result<(), Self::Error>;
}

impl<W: io::Write> Write for W {
    type Error = io::Error;

    fn write(&mut self, data: &[u8]) -> Result<(), Self::Error> {
        self.write_all(data)
    }
}

struct Formatter<'a, 'b>(&'a mut fmt::Formatter<'b>);

impl Write for Formatter<'_, '_> {
    type Error = fmt::Error;

    fn write(&mut self, data: &[u8]) -> Result<(), Self::Error> {
        self.0.write_str(unsafe { str::from_utf8_unchecked(data) })
    }
}

/// Buffer size used by `write_base64`.
const BUFFER_SIZE: usize = 1024;
/// Maximum input size that `write_base64` can process.
const CHUNK_SIZE: usize = (BUFFER_SIZE - BUFFER_SIZE % 4) * 3 / 4;

impl<W: Write> WriterImpl<W> {
    fn new(writer: W) -> Self {
        Self {
            writer,
            residual: [0; 3],
            size: 0,
        }
    }

    /// Encodes and writes `plaintext` up to the Base64 "boundary".
    fn write_base64(&mut self, plaintext: &[u8]) -> Result<usize, W::Error> {
        let mut buffer = [0u8; BUFFER_SIZE];
        let size = plaintext.len() - plaintext.len() % 3;
        let n = encode(&plaintext[..size], &mut buffer);
        self.writer.write(&buffer[..n])?;
        Ok(size)
    }

    fn fill_residual(&mut self, plaintext: &[u8]) -> usize {
        let n = cmp::min(self.residual.len() - self.size, plaintext.len());
        self.residual[self.size..self.size + n].copy_from_slice(&plaintext[..n]);
        self.size += n;
        n
    }

    /// Encodes `residual` and writes it with padding.
    fn write_residual(&mut self) -> Result<(), W::Error> {
        let mut buffer = [0u8; 4];
        let n = encode(&self.residual[..self.size], &mut buffer);
        self.writer.write(&buffer[..n])?;
        self.size = 0;
        Ok(())
    }

    fn close(&mut self) -> Result<(), W::Error> {
        self.write_residual()
        // NOTE: I am not sure if this is a good idea, but we do not call `self.writer.flush()`
        // here, and `writer` should/will flush itself when it is dropped.
    }

    fn write(&mut self, mut plaintext: &[u8]) -> Result<usize, W::Error> {
        let mut num_written = 0;

        let n = self.fill_residual(plaintext);
        plaintext = &plaintext[n..];
        num_written += n;

        if self.size == self.residual.len() {
            self.write_residual()?;
        } else if self.size > 0 {
            assert!(plaintext.is_empty());
            return Ok(num_written);
        }

        let mut chunks = plaintext.chunks_exact(CHUNK_SIZE);
        for chunk in chunks.by_ref() {
            assert_eq!(self.write_base64(chunk)?, chunk.len());
            num_written += chunk.len();
        }

        let chunk = chunks.remainder();
        let n = self.write_base64(chunk)?;
        assert_eq!(self.fill_residual(&chunk[n..]), chunk.len() - n);
        num_written += chunk.len();

        Ok(num_written)
    }
}

fn encode(input: &[u8], output: &mut [u8]) -> usize {
    STANDARD
        .encode_slice(input, output)
        .expect("g1_base64::encode")
}

#[cfg(test)]
mod tests {
    use std::io::Write as _;
    use std::iter;

    use super::*;

    #[test]
    fn writer() {
        fn test(testdata: &str, expect: &[u8]) {
            let mut buffer = Vec::new();
            std::write!(Writer::new(&mut buffer), "{testdata}").unwrap();
            assert_eq!(buffer, expect);

            assert_eq!(std::format!("{}", Display(&testdata)).as_bytes(), expect);

            assert_eq!(
                std::format!("{}", DisplayBytes(testdata.as_bytes())).as_bytes(),
                expect,
            );
        }

        test("", b"");
        test("a", b"YQ==");
        test("ab", b"YWI=");
        test("abc", b"YWJj");
        test("abcd", b"YWJjZA==");
        test("abcde", b"YWJjZGU=");
        test("abcdef", b"YWJjZGVm");
        test("Hello, World!", b"SGVsbG8sIFdvcmxkIQ==");
        test(
            "012345678901234567890123456789",
            b"MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5",
        );

        for chunk_size in 1..=14 {
            let mut buffer = Vec::new();
            {
                let mut writer = Writer::new(&mut buffer);
                for chunk in b"Hello, World!".chunks(chunk_size) {
                    writer.write_all(chunk).unwrap();
                }
                writer.close().unwrap();
            }
            assert_eq!(buffer, b"SGVsbG8sIFdvcmxkIQ==");
        }

        let testdata: String = iter::repeat("0123456789").take(9999).collect();
        let mut expect = Vec::with_capacity(10 * 9999 * 4 / 3);
        for _ in 0..3333 {
            expect.extend_from_slice(b"MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5");
        }
        test(&testdata, &expect);
    }

    #[test]
    fn display() {
        struct Pieces<'a>(&'a [&'a str]);

        impl fmt::Display for Pieces<'_> {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                for piece in self.0 {
                    f.write_str(piece)?;
                }
                Ok(())
            }
        }

        fn test(testdata: &[&str], expect: &str) {
            assert_eq!(std::format!("{}", Display(Pieces(testdata))), expect);
        }

        test(&[], "");
        test(&[""], "");
        test(&["", ""], "");

        test(&["a", ""], "YQ==");
        test(&["", "a", ""], "YQ==");

        test(&["", "a", "b"], "YWI=");
        test(&["a", "", "b", "c"], "YWJj");
        test(&["a", "", "b", "c", "", "d"], "YWJjZA==");

        for chunk_size in 1..=14 {
            let chunks = b"Hello, World!"
                .chunks(chunk_size)
                .map(|x| str::from_utf8(x).unwrap())
                .collect::<Vec<_>>();
            test(&chunks, "SGVsbG8sIFdvcmxkIQ==");
        }
    }
}
