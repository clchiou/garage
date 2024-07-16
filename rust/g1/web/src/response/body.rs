use std::cmp;
use std::fs::File;
use std::io::{Error, Read, Seek};
use std::pin::Pin;
use std::task::{Context, Poll};

use bytes::{Bytes, BytesMut};
use http_body::{Frame, SizeHint};
use http_body_util::combinators::BoxBody;
use http_body_util::{BodyExt, Empty, Full};

// At the moment, for simplicity, we assume that a response body is either a memory buffer or a
// file; thus, the error type is set to `std::io::Error`.
pub type Body = BoxBody<Bytes, Error>;

const BUFFER_SIZE: usize = 8192; // TODO: What size should we use?

pub fn empty() -> Body {
    Empty::new().map_err(|_| std::unreachable!()).boxed()
}

pub fn full(data: &'static [u8]) -> Body {
    Full::from(data).map_err(|_| std::unreachable!()).boxed()
}

pub fn file(file: File) -> Result<Body, Error> {
    Ok(FileBody::new(file, BUFFER_SIZE)?.boxed())
}

/// Response body that consists of a `File`.
///
/// Note that, unlike `tokio::fs::File`, this does not delegate file reads to a thread pool.  If
/// this does not fit your use case, consider using `http_body_util::StreamBody` instead.
#[derive(Debug)]
struct FileBody {
    file: File,
    remaining: u64,
    buffer_size: usize,
}

// TODO: Consider using a buffer pool.
impl FileBody {
    fn new(mut file: File, buffer_size: usize) -> Result<Self, Error> {
        let remaining = file.metadata()?.len() - file.stream_position()?;
        Ok(Self {
            file,
            remaining,
            buffer_size,
        })
    }

    fn read(&mut self) -> Result<Option<Bytes>, Error> {
        if self.remaining == 0 {
            return Ok(None);
        }

        // TODO: From my casual reading of the Rust source code, it appears that the stdlib has not
        // yet optimized `read_buf_exact` for `File`, instead falling back to the normal `read`.
        // Therefore, at present, it offers no performance advantage over `read_exact`.
        let mut buffer = BytesMut::zeroed(self.buffer_size);
        let n = cmp::min(
            buffer.len(),
            usize::try_from(self.remaining).expect("remaining"),
        );
        self.file
            .read_exact(&mut buffer[..n])
            .inspect_err(|_| self.remaining = 0)?;
        buffer.truncate(n);
        self.remaining -= u64::try_from(n).expect("remaining");

        Ok(Some(buffer.into()))
    }
}

impl http_body::Body for FileBody {
    type Data = Bytes;
    type Error = Error;

    fn poll_frame(
        self: Pin<&mut Self>,
        _: &mut Context<'_>,
    ) -> Poll<Option<Result<Frame<Self::Data>, Self::Error>>> {
        Poll::Ready(
            self.get_mut()
                .read()
                .map(|buffer| buffer.map(Frame::data))
                .transpose(),
        )
    }

    fn is_end_stream(&self) -> bool {
        self.remaining == 0
    }

    fn size_hint(&self) -> SizeHint {
        SizeHint::with_exact(self.remaining)
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl FileBody {
        pub(crate) fn remaining_usize(&self) -> usize {
            self.remaining.try_into().expect("remaining")
        }

        pub(crate) fn into_file(self) -> File {
            self.file
        }
    }
}

#[cfg(test)]
mod tests {
    use std::io::{SeekFrom, Write};

    use tempfile;

    use super::*;

    #[test]
    fn file_body() -> Result<(), Error> {
        const TESTDATA: &[u8] = b"hello world";

        let mut file = tempfile::tempfile()?;
        file.write_all(TESTDATA)?;

        for offset in 0..TESTDATA.len() {
            for buffer_size in 1..=TESTDATA.len() {
                file.seek(SeekFrom::Start(offset.try_into().expect("offset")))?;
                let mut remaining = TESTDATA.len() - offset;

                let mut body = FileBody::new(file, buffer_size)?;
                assert_eq!(body.remaining_usize(), remaining);

                for chunk in TESTDATA[offset..].chunks(buffer_size) {
                    assert_eq!(body.read()?.as_deref(), Some(chunk));
                    remaining -= chunk.len();
                    assert_eq!(body.remaining_usize(), remaining);
                }

                for _ in 0..3 {
                    assert_eq!(body.read()?, None);
                    assert_eq!(body.remaining_usize(), 0);
                }

                file = body.into_file();
            }
        }

        Ok(())
    }
}
