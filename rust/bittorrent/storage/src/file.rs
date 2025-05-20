use std::io::Error;
use std::path::Path;

use async_trait::async_trait;
use bytes::{Buf, BufMut, Bytes, BytesMut};
use tokio::{fs::File, io::AsyncWriteExt};

use g1_tokio::io::AsyncReadBufExact;

use bittorrent_base::{BlockDesc, Dimension, PieceIndex};
use bittorrent_metainfo::Info;

use crate::{
    Bitfield, FileBlockDesc, FileBlockOffset, PieceHash,
    coord::CoordSys,
    io::{self, PieceHasher},
    metainfo,
};

#[derive(Debug)]
pub struct Storage {
    coord_sys: CoordSys,
    piece_hashes: Vec<PieceHash>,
    files: Vec<File>,
}

impl Storage {
    /// Opens the storage.
    ///
    /// NOTE: This does not roll back (i.e., remove the created directories) on error.
    pub async fn open(info: &Info<'_>, dim: Dimension, torrent_dir: &Path) -> Result<Self, Error> {
        let paths = metainfo::new_paths(info, torrent_dir)?;
        let coord_sys = CoordSys::new(
            dim,
            paths.iter().filter_map(|(_, size)| {
                let size = *size;
                if size > 0 { Some(size) } else { None }
            }),
        )?;
        // TODO: Is there an async version of `map`?
        let mut files = Vec::with_capacity(paths.len());
        for (path, size) in paths {
            let file = io::open(&path, size).await?;
            if size > 0 {
                files.push(file);
            }
        }
        Ok(Self {
            coord_sys,
            piece_hashes: metainfo::new_piece_hashes(info),
            files,
        })
    }

    async fn prepare(&mut self, offset: FileBlockOffset) -> Result<&mut File, Error> {
        let file = &mut self.files[usize::from(offset.0)];
        offset.seek(file).await?;
        Ok(file)
    }
}

#[async_trait]
impl crate::Storage for Storage {
    async fn scan(&mut self) -> Result<Bitfield, Error> {
        // TODO: Is there an async version of `try_collect`?
        let mut bitfield = Bitfield::with_capacity(self.piece_hashes.len());
        for index in 0..self.piece_hashes.len() {
            bitfield.push(self.verify(index.into()).await?);
        }
        Ok(bitfield)
    }

    async fn verify(&mut self, index: PieceIndex) -> Result<bool, Error> {
        let mut hasher = PieceHasher::new();
        for desc in self.coord_sys.dim.block_descs(index) {
            for FileBlockDesc(offset, size) in self.coord_sys.to_file_descs(desc)? {
                let size = usize::try_from(size).unwrap();
                hasher.update(self.prepare(offset).await?, size).await?;
            }
        }
        Ok(self.piece_hashes[usize::from(index)] == hasher.finalize())
    }

    async fn read(&mut self, desc: BlockDesc, buffer: &mut BytesMut) -> Result<(), Error> {
        for FileBlockDesc(offset, size) in self.coord_sys.to_file_descs(desc)? {
            let size = usize::try_from(size).unwrap();
            assert!(buffer.remaining_mut() >= size);
            self.prepare(offset)
                .await?
                .read_buf_exact(&mut buffer.limit(size))
                .await?;
        }
        Ok(())
    }

    async fn write(&mut self, desc: BlockDesc, buffer: &mut Bytes) -> Result<(), Error> {
        for FileBlockDesc(offset, size) in self.coord_sys.to_file_descs(desc)? {
            let size = usize::try_from(size).unwrap();
            assert!(buffer.remaining() >= size);
            self.prepare(offset)
                .await?
                .write_all_buf(&mut buffer.take(size))
                .await?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use hex_literal::hex;
    use tempfile;

    use bittorrent_metainfo::{File as MetainfoFile, Mode};

    use crate::test_harness::*;

    use super::*;

    async fn assert_files(path: &Path, expect: &[u8]) {
        assert_file(&path.join("1"), &expect[0..1]).await;
        assert_file(&path.join("2"), &expect[1..2]).await;
        assert_file(&path.join("3"), &expect[2..3]).await;
        assert_file(&path.join("4"), &expect[3..9]).await;
        assert_file(&path.join("5"), &expect[9..24]).await;
        assert_file(&path.join("empty/a"), &[]).await;
        assert_file(&path.join("empty/b"), &[]).await;
        assert_file(&path.join("empty/c"), &[]).await;
        assert_file(&path.join("empty/d"), &[]).await;
    }

    fn new_info() -> Info<'static> {
        fn new_file(path: Vec<&'static str>, length: u64) -> MetainfoFile<'static> {
            let mut file = MetainfoFile::new_dummy();
            file.path = path;
            file.length = length;
            file
        }

        let mut info = Info::new_dummy();
        info.name = "test";
        info.mode = Mode::MultiFile {
            files: vec![
                new_file(vec!["empty", "a"], 0),
                new_file(vec!["1"], 1), // piece 0
                new_file(vec!["2"], 1), // piece 0
                new_file(vec!["3"], 1), // piece 0
                new_file(vec!["empty", "b"], 0),
                new_file(vec!["4"], 6), // piece 0, 1
                new_file(vec!["empty", "c"], 0),
                new_file(vec!["5"], 15), // piece 1, 2, 3
                new_file(vec!["empty", "d"], 0),
            ],
        };
        info.piece_length = 7;
        info.pieces = vec![
            hex!("77ce0377defbd11b77b1f4ad54ca40ea5ef28490").as_slice(),
            hex!("77ce0377defbd11b77b1f4ad54ca40ea5ef28490").as_slice(),
            hex!("77ce0377defbd11b77b1f4ad54ca40ea5ef28490").as_slice(),
            hex!("29e2dcfbb16f63bb0254df7585a15bb6fb5e927d").as_slice(),
        ];
        info
    }

    #[tokio::test]
    async fn scan() {
        let info = new_info();
        let dim = info.new_dimension(16384);
        let tempdir = tempfile::tempdir().unwrap();
        let mut storage = Storage::open(&info, dim, tempdir.path()).await.unwrap();
        assert_bitfield(&mut storage, &[true, true, true, true]).await;

        write(&mut storage, (1, 0, 1), b"x").await;
        assert_bitfield(&mut storage, &[true, false, true, true]).await;

        write(&mut storage, (3, 0, 1), b"x").await;
        assert_bitfield(&mut storage, &[true, false, true, false]).await;
    }

    #[tokio::test]
    async fn read_write() {
        let info = new_info();
        let dim = info.new_dimension(16384);
        let tempdir = tempfile::tempdir().unwrap();
        let path = tempdir.path().join(info.name);
        let mut storage = Storage::open(&info, dim, tempdir.path()).await.unwrap();
        assert_files(&path, &[0u8; 24]).await;

        write(&mut storage, (0, 0, 7), &hex!("11223344556677 ffff")).await;
        write(&mut storage, (1, 3, 4), &hex!("deadbeef ffff")).await;
        write(&mut storage, (2, 6, 1), &hex!("88 ffff")).await;
        write(&mut storage, (3, 0, 3), &hex!("99aabb ffff")).await;
        assert_files(
            &path,
            &hex!("11223344556677 000000deadbeef 00000000000088 99aabb"),
        )
        .await;
        read(&mut storage, (0, 0, 7), &hex!("11223344556677")).await;
        read(&mut storage, (1, 0, 7), &hex!("000000deadbeef")).await;
        read(&mut storage, (2, 0, 7), &hex!("00000000000088")).await;
        read(&mut storage, (3, 0, 3), &hex!("99aabb")).await;

        for (offset, byte) in hex!("11223344556677").into_iter().enumerate() {
            let offset = u64::try_from(offset).unwrap();
            write(&mut storage, (2, offset, 1), &[byte, 0xff, 0xff]).await;
        }
        assert_files(
            &path,
            &hex!("11223344556677 000000deadbeef 11223344556677 99aabb"),
        )
        .await;
        read(&mut storage, (2, 0, 7), &hex!("11223344556677")).await;
    }
}
