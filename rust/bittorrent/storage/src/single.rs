use std::io::Error;
use std::path::Path;

use async_trait::async_trait;
use bytes::{Buf, BufMut, Bytes, BytesMut};
use tokio::{fs::File, io::AsyncWriteExt};

use g1_tokio::io::AsyncReadBufExact;

use bittorrent_base::{BlockDesc, PieceIndex};
use bittorrent_metainfo::Info;

use crate::{
    coord::CoordSys,
    io::{self, PieceHasher},
    metainfo, Bitfield, PieceHash,
};

#[derive(Debug)]
pub struct Storage {
    coord_sys: CoordSys,
    piece_hashes: Vec<PieceHash>,
    file: File,
}

impl Storage {
    /// Opens the storage.
    ///
    /// NOTE: This does not roll back (i.e., remove the created directories) on error.
    pub async fn open(info: &Info<'_>, torrent_dir: &Path) -> Result<Self, Error> {
        let path = io::expect_dir(torrent_dir)?.join(io::expect_relpath(info.name)?);
        let size = info.length();
        let coord_sys = metainfo::new_coord_sys(info, [size].into_iter())?;
        Ok(Self {
            coord_sys,
            piece_hashes: metainfo::new_piece_hashes(info),
            file: io::open(&path, size).await?,
        })
    }

    async fn prepare(&mut self, desc: BlockDesc) -> Result<Option<usize>, Error> {
        let BlockDesc(offset, size) = self.coord_sys.check_block_desc(desc)?;
        match self.coord_sys.to_file_offset(offset)? {
            Some(file_offset) => {
                file_offset.seek(&mut self.file).await?;
                Ok(Some(size.try_into().unwrap()))
            }
            None => Ok(None),
        }
    }

    // NOTE: Caller must seek the file.
    async fn compute_piece_hash(&mut self, piece_size: usize) -> Result<PieceHash, Error> {
        let mut hasher = PieceHasher::new();
        hasher.update(&mut self.file, piece_size).await?;
        Ok(hasher.finalize())
    }
}

#[async_trait]
impl crate::Storage for Storage {
    async fn scan(&mut self) -> Result<Bitfield, Error> {
        let mut bitfield = Bitfield::with_capacity(self.piece_hashes.len());
        let _ = self.prepare((0, 0, 0).into()).await?.unwrap();
        for index in 0..self.piece_hashes.len() {
            let piece_hash = self
                .compute_piece_hash(self.coord_sys.piece_size(index.into()).try_into().unwrap())
                .await?;
            bitfield.push(self.piece_hashes[index] == piece_hash);
        }
        Ok(bitfield)
    }

    async fn verify(&mut self, index: PieceIndex) -> Result<bool, Error> {
        let size = self.coord_sys.piece_size(index);
        let index = usize::from(index);
        let size = self.prepare((index, 0, size).into()).await?.unwrap();
        let piece_hash = self.compute_piece_hash(size).await?;
        Ok(self.piece_hashes[index] == piece_hash)
    }

    async fn read(&mut self, desc: BlockDesc, buffer: &mut BytesMut) -> Result<(), Error> {
        let size = self.prepare(desc).await?.unwrap_or(0);
        assert!(buffer.remaining_mut() >= size);
        self.file.read_buf_exact(&mut buffer.limit(size)).await
    }

    async fn write(&mut self, desc: BlockDesc, buffer: &mut Bytes) -> Result<(), Error> {
        let size = self.prepare(desc).await?.unwrap_or(0);
        assert!(buffer.remaining() >= size);
        self.file.write_all_buf(&mut buffer.take(size)).await
    }
}

#[cfg(test)]
mod tests {
    use hex_literal::hex;
    use tempfile;

    use bittorrent_metainfo::Mode;

    use crate::test_harness::*;

    use super::*;

    fn new_info() -> Info<'static> {
        let mut info = Info::new_dummy();
        info.name = "test";
        info.mode = Mode::SingleFile {
            length: 10,
            md5sum: None,
        };
        info.piece_length = 7;
        info.pieces = vec![
            hex!("77ce0377defbd11b77b1f4ad54ca40ea5ef28490").as_slice(),
            hex!("29e2dcfbb16f63bb0254df7585a15bb6fb5e927d").as_slice(),
        ];
        info
    }

    #[tokio::test]
    async fn scan() {
        let info = new_info();
        let tempdir = tempfile::tempdir().unwrap();
        let mut storage = Storage::open(&info, tempdir.path()).await.unwrap();
        assert_bitfield(&mut storage, &[true, true]).await;

        write(&mut storage, (1, 0, 1), b"x").await;
        assert_bitfield(&mut storage, &[true, false]).await;

        write(&mut storage, (0, 0, 1), b"x").await;
        assert_bitfield(&mut storage, &[false, false]).await;
    }

    #[tokio::test]
    async fn read_write() {
        let info = new_info();
        let tempdir = tempfile::tempdir().unwrap();
        let path = tempdir.path().join(info.name);
        let mut storage = Storage::open(&info, tempdir.path()).await.unwrap();
        assert_file(&path, &hex!("00 00 00 00 00 00 00 00 00 00")).await;

        write(&mut storage, (0, 3, 3), &hex!("11 22 33 ff")).await;
        assert_file(&path, &hex!("00 00 00 11 22 33 00 00 00 00")).await;

        write(&mut storage, (1, 1, 1), &hex!("44 ff")).await;
        assert_file(&path, &hex!("00 00 00 11 22 33 00 00 44 00")).await;

        read(&mut storage, (0, 0, 7), &hex!("00 00 00 11 22 33 00")).await;
        read(&mut storage, (0, 2, 4), &hex!("00 11 22 33")).await;
        read(&mut storage, (1, 0, 3), &hex!("00 44 00")).await;

        write(&mut storage, (0, 5, 2), &hex!("55 66 ff")).await;
        assert_file(&path, &hex!("00 00 00 11 22 55 66 00 44 00")).await;
        read(&mut storage, (0, 0, 7), &hex!("00 00 00 11 22 55 66")).await;

        read(&mut storage, (0, 0, 0), &[]).await;
        read(&mut storage, (0, 6, 0), &[]).await;
        read(&mut storage, (1, 2, 0), &[]).await;
        read(&mut storage, (1, 3, 0), &[]).await;

        write(&mut storage, (0, 0, 0), &[]).await;
        write(&mut storage, (0, 6, 0), &[]).await;
        write(&mut storage, (1, 2, 0), &[]).await;
        write(&mut storage, (1, 3, 0), &[]).await;
        assert_file(&path, &hex!("00 00 00 11 22 55 66 00 44 00")).await;
    }
}
