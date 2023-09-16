#![feature(io_error_other)]
#![feature(iterator_try_collect)]

pub mod error;

mod coord;
mod io;

use std::io::Error;

use async_trait::async_trait;
use bitvec::prelude::*;
use bytes::{Bytes, BytesMut};
use tokio::{
    fs::File,
    io::{AsyncSeekExt, SeekFrom},
};

use bittorrent_base::{BlockDesc, PieceIndex, PIECE_HASH_SIZE};

#[async_trait]
pub trait Storage {
    async fn scan(&mut self) -> Result<BitVec, Error>;

    async fn verify(&mut self, index: PieceIndex) -> Result<bool, Error>;

    // Use a concrete type rather than `impl BufMut` so that we can create trait objects for
    // `Storage`.
    async fn read(&mut self, desc: BlockDesc, buffer: &mut BytesMut) -> Result<(), Error>;

    // Use a concrete type for the same reason above.
    async fn write(&mut self, desc: BlockDesc, buffer: &mut Bytes) -> Result<(), Error>;
}

pub(crate) type PieceHash = [u8; PIECE_HASH_SIZE];

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub(crate) struct FileIndex(pub(crate) usize);

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub(crate) struct FileBlockOffset(pub(crate) FileIndex, pub(crate) u64);

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub(crate) struct FileBlockDesc(pub(crate) FileBlockOffset, pub(crate) u64);

impl From<usize> for FileIndex {
    fn from(index: usize) -> Self {
        Self(index)
    }
}

impl From<FileIndex> for usize {
    fn from(FileIndex(index): FileIndex) -> Self {
        index
    }
}

impl From<(usize, u64)> for FileBlockOffset {
    fn from((index, offset): (usize, u64)) -> Self {
        Self(index.into(), offset)
    }
}

impl From<(FileIndex, u64)> for FileBlockOffset {
    fn from((index, offset): (FileIndex, u64)) -> Self {
        Self(index, offset)
    }
}

impl From<FileBlockOffset> for (usize, u64) {
    fn from(FileBlockOffset(FileIndex(index), offset): FileBlockOffset) -> Self {
        (index, offset)
    }
}

impl FileBlockOffset {
    pub(crate) async fn seek(&self, file: &mut File) -> Result<(), Error> {
        assert_eq!(file.seek(SeekFrom::Start(self.1)).await?, self.1);
        Ok(())
    }
}

impl From<(usize, u64, u64)> for FileBlockDesc {
    fn from((index, offset, size): (usize, u64, u64)) -> Self {
        Self((index, offset).into(), size)
    }
}

impl From<(FileBlockOffset, u64)> for FileBlockDesc {
    fn from((offset, size): (FileBlockOffset, u64)) -> Self {
        Self(offset, size)
    }
}

#[cfg(test)]
mod test_harness {
    use std::path::Path;

    use tokio::fs;

    use super::*;

    pub(crate) async fn assert_bitfield(storage: &mut impl Storage, expect: &[bool]) {
        let bitfield: BitVec = expect.iter().collect();
        assert_eq!(storage.scan().await.unwrap(), bitfield);
        for (i, expect) in expect.iter().copied().enumerate() {
            assert_eq!(storage.verify(i.into()).await.unwrap(), expect);
        }
    }

    pub(crate) async fn assert_file(path: &Path, expect: &[u8]) {
        assert_eq!(fs::read(path).await.unwrap(), expect);
    }

    pub(crate) async fn read(storage: &mut impl Storage, desc: (usize, u64, u64), expect: &[u8]) {
        let mut buffer = BytesMut::new();
        storage.read(desc.into(), &mut buffer).await.unwrap();
        assert_eq!(buffer, expect);
    }

    pub(crate) async fn write(storage: &mut impl Storage, desc: (usize, u64, u64), data: &[u8]) {
        storage
            .write(desc.into(), &mut Bytes::copy_from_slice(data))
            .await
            .unwrap();
    }
}
