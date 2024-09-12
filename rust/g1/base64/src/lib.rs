use std::cmp;
use std::io::{Error, Write};

use base64::engine::general_purpose::STANDARD;
use base64::Engine as _;

pub struct Writer<W>
where
    W: Write,
{
    writer: W,
    residual: [u8; 3],
    size: usize,
}

impl<W> Drop for Writer<W>
where
    W: Write,
{
    fn drop(&mut self) {
        self.close_impl().expect("Writer::close");
    }
}

/// Buffer size used by `write_base64`.
const BUFFER_SIZE: usize = 1024;
/// Maximum input size that `write_base64` can process.
const CHUNK_SIZE: usize = (BUFFER_SIZE - BUFFER_SIZE % 4) * 3 / 4;

impl<W> Writer<W>
where
    W: Write,
{
    pub fn new(writer: W) -> Self {
        Self {
            writer,
            residual: [0; 3],
            size: 0,
        }
    }

    /// Encodes and writes `plaintext` up to the Base64 "boundary".
    fn write_base64(&mut self, plaintext: &[u8]) -> Result<usize, Error> {
        let mut buffer = [0u8; BUFFER_SIZE];
        let size = plaintext.len() - plaintext.len() % 3;
        let n = encode(&plaintext[..size], &mut buffer);
        self.writer.write_all(&buffer[..n])?;
        Ok(size)
    }

    fn fill_residual(&mut self, plaintext: &[u8]) -> usize {
        let n = cmp::min(self.residual.len() - self.size, plaintext.len());
        self.residual[self.size..self.size + n].copy_from_slice(&plaintext[..n]);
        self.size += n;
        n
    }

    /// Encodes `residual` and writes it with padding.
    fn write_residual(&mut self) -> Result<(), Error> {
        let mut buffer = [0u8; 4];
        let n = encode(&self.residual[..self.size], &mut buffer);
        self.writer.write_all(&buffer[..n])?;
        self.size = 0;
        Ok(())
    }

    pub fn close(mut self) -> Result<(), Error> {
        self.close_impl()
    }

    fn close_impl(&mut self) -> Result<(), Error> {
        self.write_residual()
        // NOTE: I am not sure if this is a good idea, but we do not call `self.writer.flush()`
        // here, and `writer` should/will flush itself when it is dropped.
    }
}

impl<W> Write for Writer<W>
where
    W: Write,
{
    fn write(&mut self, mut plaintext: &[u8]) -> Result<usize, Error> {
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

    fn flush(&mut self) -> Result<(), Error> {
        self.writer.flush()
    }
}

fn encode(input: &[u8], output: &mut [u8]) -> usize {
    STANDARD
        .encode_slice(input, output)
        .expect("g1_base64::encode")
}

#[cfg(test)]
mod tests {
    use std::iter;

    use super::*;

    #[test]
    fn writer() {
        fn test(testdata: &str, expect: &[u8]) {
            let mut buffer = Vec::new();
            std::write!(Writer::new(&mut buffer), "{testdata}").unwrap();
            assert_eq!(buffer, expect);
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
}
