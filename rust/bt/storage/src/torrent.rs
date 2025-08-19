use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::ops::Range;

use digest::Digest;
use md5::Md5;
use sha1::Sha1;
use snafu::prelude::*;

use bt_base::md5_hash::MD5_HASH_SIZE;
use bt_base::piece_hash::PIECE_HASH_SIZE;
use bt_base::{Bitfield, BlockRange, Layout, PieceIndex};
use bt_metainfo::Info;

use crate::error::{
    BufferOverflowSnafu, Error, InvalidBlockRangeSnafu, InvalidPieceIndexSnafu, IoSnafu,
};
use crate::storage_dir::TorrentGuard;

#[derive(Debug)]
pub struct Torrent {
    torrent: File,
    layout: Layout,
    info: Info,
    _guard: TorrentGuard,
}

#[derive(Debug)]
pub struct TorrentFile<'a>(&'a mut Torrent, usize);

impl Torrent {
    pub(crate) fn new(torrent: File, layout: Layout, info: Info, guard: TorrentGuard) -> Self {
        Self {
            torrent,
            layout,
            info,
            _guard: guard,
        }
    }

    fn seek(&mut self, offset: u64) -> Result<(), Error> {
        let pos = self
            .torrent
            .seek(SeekFrom::Start(offset))
            .context(IoSnafu)?;
        assert_eq!(pos, offset);
        Ok(())
    }

    fn compute_hash<H>(&mut self, hasher: &mut H, size: u64) -> Result<(), Error>
    where
        H: Digest,
    {
        let mut buffer = [0u8; 4096]; // TODO: What buffer size should we use?
        let mut size = usize::try_from(size).expect("size");
        while size > 0 {
            let buf_size = buffer.len().min(size);
            let buf = &mut buffer[0..buf_size];
            self.torrent.read_exact(buf).context(IoSnafu)?;
            hasher.update(buf);
            size -= buf_size;
        }
        Ok(())
    }

    //
    // Piece I/O interface.
    //

    pub fn scan(&mut self) -> Result<Bitfield, Error> {
        self.scan_consecutive(PieceIndex(0)..PieceIndex(self.layout.num_pieces()))
    }

    fn scan_consecutive(&mut self, index_range: Range<PieceIndex>) -> Result<Bitfield, Error> {
        let mut bitfield = Bitfield::with_capacity(index_range.clone().count());
        self.seek_piece(index_range.start)?;
        let pieces = self.info.pieces();
        for index in index_range {
            let actual = self.compute_piece_hash(self.layout.piece_size(index))?;
            let expect = pieces
                .get(usize::try_from(index.0).expect("index"))
                .expect("piece_hash");
            bitfield.push(actual == expect.as_ref());
        }
        Ok(bitfield)
    }

    pub fn verify(&mut self, index: PieceIndex) -> Result<bool, Error> {
        ensure!(
            self.layout.check_index(index),
            InvalidPieceIndexSnafu { index }
        );

        self.seek_piece(index)?;
        let actual = self.compute_piece_hash(self.layout.piece_size(index))?;

        let pieces = self.info.pieces();
        let expect = pieces
            .get(usize::try_from(index.0).expect("index"))
            .expect("piece_hash");

        Ok(actual == expect.as_ref())
    }

    fn seek_piece(&mut self, index: PieceIndex) -> Result<(), Error> {
        self.seek_block(BlockRange(index, 0, 0))
    }

    fn compute_piece_hash(&mut self, size: u64) -> Result<[u8; PIECE_HASH_SIZE], Error> {
        let mut hasher = Sha1::new();
        self.compute_hash(&mut hasher, size)?;
        Ok(hasher.finalize().into())
    }

    //
    // Block I/O interface.
    //

    fn ensure_range(&self, range: BlockRange, len: usize) -> Result<usize, Error> {
        ensure!(
            self.layout.check_range(range),
            InvalidBlockRangeSnafu { range }
        );

        let size = usize::try_from(range.2).expect("size");
        ensure!(len >= size, BufferOverflowSnafu { len, size });

        Ok(size)
    }

    pub fn read(&mut self, range: BlockRange, buffer: &mut [u8]) -> Result<(), Error> {
        let size = self.ensure_range(range, buffer.len())?;
        self.seek_block(range)?;
        self.torrent
            .read_exact(&mut buffer[0..size])
            .context(IoSnafu)
    }

    pub fn write(&mut self, range: BlockRange, buffer: &[u8]) -> Result<(), Error> {
        let size = self.ensure_range(range, buffer.len())?;
        self.seek_block(range)?;
        self.torrent.write_all(&buffer[0..size]).context(IoSnafu)
    }

    fn seek_block(&mut self, range: BlockRange) -> Result<(), Error> {
        self.seek(self.layout.piece_offset(range.0) + range.1)
    }

    //
    // Interface used to access the files in a torrent.
    //

    pub fn is_empty(&self) -> bool {
        self.info.is_empty()
    }

    pub fn len(&self) -> usize {
        self.info.len()
    }

    pub fn get(&mut self, i: usize) -> TorrentFile<'_> {
        assert!(i < self.len());
        TorrentFile(self, i)
    }

    /// Seeks the torrent to the start of the file and returns its size.
    pub fn prepare_splice(&mut self, i: usize) -> Result<usize, Error> {
        let (offset, size) = self.info.file_range(i);
        self.seek(offset)?;
        Ok(size.try_into().expect("usize"))
    }

    fn compute_file_hash(&mut self, size: u64) -> Result<[u8; MD5_HASH_SIZE], Error> {
        let mut hasher = Md5::new();
        self.compute_hash(&mut hasher, size)?;
        Ok(hasher.finalize().into())
    }
}

// NOTE: We do not implement `BorrowMut` because it requires `Borrow`, and returning a `&File`
// would be unsafe in our use case (`splice`-ing the file).
impl AsMut<File> for Torrent {
    fn as_mut(&mut self) -> &mut File {
        &mut self.torrent
    }
}

impl<'a> TorrentFile<'a> {
    pub fn verify_md5sum(&mut self) -> Result<Option<bool>, Error> {
        let Some(expect) = self.0.info.file(self.1).md5sum else {
            return Ok(None);
        };

        let (offset, size) = self.0.info.file_range(self.1);

        self.0.seek(offset)?;
        let actual = self.0.compute_file_hash(size)?;

        Ok(Some(actual == expect.as_ref()))
    }

    //
    // Piece I/O interface.
    //

    pub fn index_range(&self) -> Range<PieceIndex> {
        let (offset, size) = self.0.info.file_range(self.1);

        let (start, _) = self.0.layout.to_piece_index(offset);

        let (mut end, end_offset) = self.0.layout.to_piece_index(offset + size);
        if end_offset > 0 && size > 0 {
            end = PieceIndex(end.0 + 1);
        }

        start..end
    }

    pub fn scan(&mut self) -> Result<Bitfield, Error> {
        self.0.scan_consecutive(self.index_range())
    }

    pub fn verify(&mut self, index: PieceIndex) -> Result<bool, Error> {
        self.0.verify(index)
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use bitvec::prelude::*;

    use bt_base::InfoHash;

    use crate::Storage;
    use crate::testing::mock_info;

    use super::*;

    fn write_torrent(torrent: &mut Torrent, offset: u64, data: &[u8]) {
        assert_matches!(torrent.seek(offset), Ok(()));
        assert_matches!(torrent.as_mut().write_all(data), Ok(()));
    }

    fn assert_torrent(torrent: &mut Torrent, expect: &[u8]) {
        assert_matches!(torrent.seek(0), Ok(()));
        let mut actual = Vec::new();
        assert_matches!(torrent.as_mut().read_to_end(&mut actual), Ok(_));
        assert_eq!(actual, expect);
    }

    #[test]
    fn scan_and_verify() {
        fn test(torrent: &mut Torrent, expect: &BitSlice) {
            assert_matches!(torrent.scan(), Ok(bitfield) if bitfield == expect);

            for (index, expect_verify) in expect.iter().by_vals().enumerate() {
                let index = PieceIndex(index.try_into().unwrap());
                assert_matches!(torrent.verify(index), Ok(verify) if verify == expect_verify);
            }
        }

        let info = mock_info("foo", b"abcdefg", 2, &[]);
        let info_hash = InfoHash::digest(&bt_bencode::to_bytes(&info).unwrap());

        let tempdir = tempfile::tempdir().unwrap();
        let storage = Storage::open(tempdir.path()).unwrap();
        assert_matches!(storage.insert_info(info), Ok(true));
        let mut torrent = storage.open_torrent(info_hash).unwrap().unwrap();
        test(&mut torrent, bits![0, 0, 0, 0]);

        write_torrent(&mut torrent, 0, b"ab");
        test(&mut torrent, bits![1, 0, 0, 0]);

        write_torrent(&mut torrent, 6, b"g");
        test(&mut torrent, bits![1, 0, 0, 1]);

        write_torrent(&mut torrent, 2, b"cd");
        test(&mut torrent, bits![1, 1, 0, 1]);

        write_torrent(&mut torrent, 4, b"ef");
        test(&mut torrent, bits![1, 1, 1, 1]);
    }

    #[test]
    fn read() {
        let info = mock_info("foo", b"abcdefg", 4, &[]);
        let info_hash = InfoHash::digest(&bt_bencode::to_bytes(&info).unwrap());

        let tempdir = tempfile::tempdir().unwrap();
        let storage = Storage::open(tempdir.path()).unwrap();
        assert_matches!(storage.insert_info(info), Ok(true));
        let mut torrent = storage.open_torrent(info_hash).unwrap().unwrap();
        write_torrent(&mut torrent, 0, b"abcdefg");

        let mut data = [0; 8];

        assert_matches!(
            torrent.read(BlockRange(PieceIndex(0), 1, 3), &mut data[0..3]),
            Ok(()),
        );
        assert_eq!(&data[0..3], b"bcd");

        assert_matches!(
            torrent.read(BlockRange(PieceIndex(1), 0, 3), &mut data[0..3]),
            Ok(()),
        );
        assert_eq!(&data[0..3], b"efg");

        assert_matches!(
            torrent.read(BlockRange(PieceIndex(0), 2, 3), &mut data),
            Err(Error::InvalidBlockRange { .. }),
        );
        assert_matches!(
            torrent.read(BlockRange(PieceIndex(0), 0, 4), &mut data[0..3]),
            Err(Error::BufferOverflow { len: 3, size: 4 }),
        );
    }

    #[test]
    fn write() {
        let info = mock_info("foo", b"abcdefg", 4, &[]);
        let info_hash = InfoHash::digest(&bt_bencode::to_bytes(&info).unwrap());

        let tempdir = tempfile::tempdir().unwrap();
        let storage = Storage::open(tempdir.path()).unwrap();
        assert_matches!(storage.insert_info(info), Ok(true));
        let mut torrent = storage.open_torrent(info_hash).unwrap().unwrap();
        assert_torrent(&mut torrent, b"\x00\x00\x00\x00\x00\x00\x00");

        assert_matches!(
            torrent.write(BlockRange(PieceIndex(0), 1, 3), b"xyz"),
            Ok(()),
        );
        assert_torrent(&mut torrent, b"\x00xyz\x00\x00\x00");

        assert_matches!(
            torrent.write(BlockRange(PieceIndex(1), 0, 3), b"pqr"),
            Ok(()),
        );
        assert_torrent(&mut torrent, b"\x00xyzpqr");

        assert_matches!(
            torrent.write(BlockRange(PieceIndex(0), 2, 3), b"abc"),
            Err(Error::InvalidBlockRange { .. }),
        );
        assert_matches!(
            torrent.write(BlockRange(PieceIndex(0), 0, 4), b"abc"),
            Err(Error::BufferOverflow { len: 3, size: 4 }),
        );
    }

    #[test]
    fn torrent_file_single() {
        let info = mock_info("foo", b"abcdefg", 4, &[]);
        let info_hash = InfoHash::digest(&bt_bencode::to_bytes(&info).unwrap());

        let tempdir = tempfile::tempdir().unwrap();
        let storage = Storage::open(tempdir.path()).unwrap();
        assert_matches!(storage.insert_info(info), Ok(true));
        let mut torrent = storage.open_torrent(info_hash).unwrap().unwrap();

        assert_eq!(torrent.len(), 1);
        assert_eq!(torrent.get(0).index_range(), PieceIndex(0)..PieceIndex(2));

        {
            let mut torrent_file = torrent.get(0);
            assert_matches!(torrent_file.verify_md5sum(), Ok(Some(false)));
            assert_matches!(torrent_file.scan(), Ok(bitfield) if bitfield == bits![0, 0]);
        }

        write_torrent(&mut torrent, 4, b"efg");
        {
            let mut torrent_file = torrent.get(0);
            assert_matches!(torrent_file.verify_md5sum(), Ok(Some(false)));
            assert_matches!(torrent_file.scan(), Ok(bitfield) if bitfield == bits![0, 1]);
        }

        write_torrent(&mut torrent, 0, b"abcd");
        {
            let mut torrent_file = torrent.get(0);
            assert_matches!(torrent_file.verify_md5sum(), Ok(Some(true)));
            assert_matches!(torrent_file.scan(), Ok(bitfield) if bitfield == bits![1, 1]);
        }
    }

    #[test]
    fn torrent_file_multiple() {
        let info = mock_info(
            "foo",
            b"abcdefg",
            4,
            &[
                (&["z"], 0),
                (&["p"], 2),
                (&["z"], 0),
                (&["q"], 4),
                (&["z"], 0),
                (&["r"], 1),
                (&["z"], 0),
            ],
        );
        let info_hash = InfoHash::digest(&bt_bencode::to_bytes(&info).unwrap());

        let tempdir = tempfile::tempdir().unwrap();
        let storage = Storage::open(tempdir.path()).unwrap();
        assert_matches!(storage.insert_info(info), Ok(true));
        let mut torrent = storage.open_torrent(info_hash).unwrap().unwrap();

        assert_eq!(torrent.len(), 7);
        for (i, expect) in [
            PieceIndex(0)..PieceIndex(0),
            PieceIndex(0)..PieceIndex(1),
            PieceIndex(0)..PieceIndex(0),
            PieceIndex(0)..PieceIndex(2),
            PieceIndex(1)..PieceIndex(1),
            PieceIndex(1)..PieceIndex(2),
            PieceIndex(1)..PieceIndex(1),
        ]
        .into_iter()
        .enumerate()
        {
            assert_eq!(torrent.get(i).index_range(), expect);
        }

        for (i, (expect_verify, expect)) in [
            (true, bits![]),
            (false, bits![0]),
            (true, bits![]),
            (false, bits![0, 0]),
            (true, bits![]),
            (false, bits![0]),
            (true, bits![]),
        ]
        .into_iter()
        .enumerate()
        {
            let mut torrent_file = torrent.get(i);
            assert_matches!(
                torrent_file.verify_md5sum(),
                Ok(Some(verify)) if verify == expect_verify,
            );
            assert_matches!(torrent_file.scan(), Ok(bitfield) if bitfield == expect);
        }

        write_torrent(&mut torrent, 4, b"efg");
        for (i, (expect_verify, expect)) in [
            (true, bits![]),
            (false, bits![0]),
            (true, bits![]),
            (false, bits![0, 1]),
            (true, bits![]),
            (true, bits![1]),
            (true, bits![]),
        ]
        .into_iter()
        .enumerate()
        {
            let mut torrent_file = torrent.get(i);
            assert_matches!(
                torrent_file.verify_md5sum(),
                Ok(Some(verify)) if verify == expect_verify,
            );
            assert_matches!(torrent_file.scan(), Ok(bitfield) if bitfield == expect);
        }

        write_torrent(&mut torrent, 0, b"abcd");
        for (i, (expect_verify, expect)) in [
            (true, bits![]),
            (true, bits![1]),
            (true, bits![]),
            (true, bits![1, 1]),
            (true, bits![]),
            (true, bits![1]),
            (true, bits![]),
        ]
        .into_iter()
        .enumerate()
        {
            let mut torrent_file = torrent.get(i);
            assert_matches!(
                torrent_file.verify_md5sum(),
                Ok(Some(verify)) if verify == expect_verify,
            );
            assert_matches!(torrent_file.scan(), Ok(bitfield) if bitfield == expect);
        }
    }
}
