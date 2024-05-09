use std::io;
use std::net::TcpStream;
use std::os::fd::AsFd;

use snafu::prelude::*;
use tokio::io::AsyncWriteExt;
use tokio::net::TcpStream as AsyncTcpStream;
use tokio::time;

use g1_tokio::os::{SendFile, Splice};

use ddcache_rpc::{BlobRequest, Token};

use crate::error::{Error, IoSnafu, PartialIoSnafu};

#[derive(Debug)]
pub struct RemoteBlob(BlobRequest);

macro_rules! io {
    ($expect:ident, $io:expr $(,)?) => {
        time::timeout(*crate::blob_request_timeout(), async move {
            let size: Result<usize, io::Error> = try { $io };
            let size = size.context(IoSnafu)?;
            ensure!(
                size == $expect,
                PartialIoSnafu {
                    size,
                    expect: $expect,
                },
            );
            Ok(())
        })
        .await
        .map_err(|_| Error::BlobRequestTimeout)?
    };
}

impl From<BlobRequest> for RemoteBlob {
    fn from(blob: BlobRequest) -> Self {
        Self::new(blob)
    }
}

impl RemoteBlob {
    pub(crate) fn new(blob: BlobRequest) -> Self {
        Self(blob)
    }

    pub fn token(&self) -> Token {
        self.0.token
    }

    async fn connect(&self) -> Result<TcpStream, io::Error> {
        let mut stream = AsyncTcpStream::connect(self.0.endpoint).await?;
        stream.write_u64(self.0.token).await?;
        // Unregister `stream` from the tokio reactor; otherwise, `sendfile` will return `EEXIST`
        // when it attempts to register `stream` with the reactor via `AsyncFd`.
        stream.into_std()
    }

    pub async fn read<F>(self, output: &mut F, expect: usize) -> Result<(), Error>
    where
        F: AsFd + Send,
    {
        io!(expect, self.connect().await?.splice(output, expect).await?)
    }

    pub async fn write<F>(self, input: &mut F, expect: usize) -> Result<(), Error>
    where
        F: AsFd + Send,
    {
        // TODO: Should we use TCP_CORK here?
        io!(
            expect,
            input.splice(&mut self.connect().await?, expect).await?,
        )
    }

    pub async fn write_file<F>(
        self,
        input: &mut F,
        offset: Option<i64>,
        expect: usize,
    ) -> Result<(), Error>
    where
        F: AsFd + Send,
    {
        // TODO: Should we use TCP_CORK here?
        io!(
            expect,
            self.connect()
                .await?
                .sendfile(input, offset, expect)
                .await?,
        )
    }
}
