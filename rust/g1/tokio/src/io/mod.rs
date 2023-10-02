mod bstream;
mod traitobj;

use std::io::{Error, ErrorKind};

use async_trait::async_trait;
use bytes::BufMut;
use tokio::io::AsyncReadExt;

pub use self::bstream::{RecvStream, SendStream, Stream};
pub use self::traitobj::{DynStream, DynStreamRecv, DynStreamSend};

#[async_trait]
pub trait AsyncReadBufExact: AsyncReadExt {
    async fn read_buf_exact<B>(&mut self, buf: &mut B) -> Result<(), Error>
    where
        Self: Sized + Unpin,
        B: BufMut + Send,
    {
        while buf.has_remaining_mut() {
            if self.read_buf(buf).await? == 0 {
                return Err(ErrorKind::UnexpectedEof.into());
            }
        }
        Ok(())
    }
}

impl<R: AsyncReadExt> AsyncReadBufExact for R {}

#[cfg(test)]
mod tests {
    use bytes::BytesMut;

    use super::*;

    #[tokio::test]
    async fn read_buf_exact() {
        async fn read_buf_exact<'a, B: BufMut + Send>(
            mut reader: &'a [u8],
            buf: &mut B,
        ) -> Result<&'a [u8], Error> {
            reader.read_buf_exact(buf).await?;
            Ok(reader)
        }

        let mut buf = [0u8; 5];
        assert_eq!(
            read_buf_exact(b"hello world", &mut buf.as_mut_slice())
                .await
                .unwrap(),
            b" world",
        );
        assert_eq!(&buf, b"hello");

        let mut buf = BytesMut::new();
        assert_eq!(
            read_buf_exact(b"hello world", &mut (&mut buf).limit(5))
                .await
                .unwrap(),
            b" world",
        );
        assert_eq!(buf, b"hello".as_slice());

        assert_eq!(
            read_buf_exact(b"hello world", &mut BytesMut::new())
                .await
                .unwrap_err()
                .kind(),
            ErrorKind::UnexpectedEof,
        );
    }
}
