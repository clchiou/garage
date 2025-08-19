use std::path::PathBuf;

use bytes::Bytes;
use const_format::formatcp;
use rusqlite::Connection;
use serde::de::DeserializeOwned;
use snafu::prelude::*;

use g1_rusqlite::{Apply, ConnectionExt, Create, Init, ReadWrite};

use bt_base::InfoHash;
use bt_base::info_hash::INFO_HASH_SIZE;
use bt_metainfo::{Info, Metainfo, SanityCheck};

use crate::error::{
    BencodeSnafu, Error, MetadataInsaneSnafu, MetadataTrailingDataSnafu, SqliteSnafu,
};

#[derive(Debug)]
pub(crate) struct MetadataDb(Pool);

type Pool = g1_rusqlite::Pool<Apply<ReadWrite, InitCacheCapacity>>;

#[derive(Debug)]
struct InitCacheCapacity;

#[derive(Debug)]
struct CreateDatabase;

const POOL_SIZE: usize = 4;

const TORRENT: &str = "torrent";

const INFO_HASH: &str = "info_hash";
const INFO: &str = "info";
const METAINFO: &str = "metainfo";

impl Init for InitCacheCapacity {
    fn init(conn: &Connection) -> Result<(), rusqlite::Error> {
        // This should be enough to "cache" all queries.
        conn.set_prepared_statement_cache_capacity(8);
        Ok(())
    }
}

impl Create for CreateDatabase {
    fn create(conn: &Connection) -> Result<(), rusqlite::Error> {
        conn.execute_batch(include_str!("storage.sql"))?;
        Ok(())
    }
}

impl MetadataDb {
    pub(crate) fn open(metadata_db: PathBuf) -> Result<Self, Error> {
        Pool::with_size::<CreateDatabase>(metadata_db, POOL_SIZE)
            .map(Self)
            .context(SqliteSnafu)
    }

    pub(crate) fn list(&self) -> Result<Vec<InfoHash>, Error> {
        let result: Result<_, _> = try {
            self.0
                .connect()?
                .vector(formatcp!("SELECT {INFO_HASH} FROM {TORRENT}"), [], |row| {
                    Ok(row.get::<_, [u8; INFO_HASH_SIZE]>(0)?.into())
                })?
        };
        result.context(SqliteSnafu)
    }

    pub(crate) fn get_metainfo(&self, info_hash: InfoHash) -> Result<Option<Metainfo>, Error> {
        Ok(self.get_metainfo_blob(info_hash)?.map(reader_decode))
    }

    pub(crate) fn get_info(&self, info_hash: InfoHash) -> Result<Option<Info>, Error> {
        Ok(self.get_info_blob(info_hash)?.map(reader_decode))
    }

    // NOTE: This does not check for data corruption.
    pub(crate) fn get_metainfo_blob(&self, info_hash: InfoHash) -> Result<Option<Bytes>, Error> {
        self.get_blob(
            formatcp!(
                "SELECT {METAINFO} FROM {TORRENT} WHERE {INFO_HASH} = ?1 AND {METAINFO} IS NOT NULL"
            ),
            info_hash,
        )
    }

    // NOTE: This does not check for data corruption.
    pub(crate) fn get_info_blob(&self, info_hash: InfoHash) -> Result<Option<Bytes>, Error> {
        self.get_blob(
            formatcp!("SELECT {INFO} FROM {TORRENT} WHERE {INFO_HASH} = ?1"),
            info_hash,
        )
    }

    fn get_blob(&self, sql: &str, info_hash: InfoHash) -> Result<Option<Bytes>, Error> {
        let result: Result<_, _> = try {
            self.0
                .connect()?
                .optional(sql, [info_hash.as_ref() as &[u8]], |row| {
                    row.get::<_, Vec<u8>>(0).map(Bytes::from)
                })?
        };
        result.context(SqliteSnafu)
    }

    pub(crate) fn insert_metainfo(&self, metainfo: Metainfo) -> Result<bool, Error> {
        metainfo.sanity_check().context(MetadataInsaneSnafu)?;
        let metainfo_blob = bt_bencode::to_bytes(&metainfo).context(BencodeSnafu)?;
        self.insert(
            metainfo.info_hash(),
            metainfo.info_blob(),
            Some(&metainfo_blob),
        )
    }

    pub(crate) fn insert_info(&self, info: Info) -> Result<bool, Error> {
        info.sanity_check().context(MetadataInsaneSnafu)?;
        let info_blob = bt_bencode::to_bytes(&info).context(BencodeSnafu)?;
        self.insert(InfoHash::digest(&info_blob), &info_blob, None)
    }

    pub(crate) fn insert_metainfo_blob(&self, metainfo_blob: &[u8]) -> Result<bool, Error> {
        let metainfo = writer_decode::<Metainfo>(metainfo_blob)?;
        self.insert(
            metainfo.info_hash(),
            metainfo.info_blob(),
            Some(metainfo_blob),
        )
    }

    pub(crate) fn insert_info_blob(&self, info_blob: &[u8]) -> Result<bool, Error> {
        let _ = writer_decode::<Info>(info_blob)?;
        self.insert(InfoHash::digest(info_blob), info_blob, None)
    }

    fn insert(
        &self,
        info_hash: InfoHash,
        info_blob: &[u8],
        metainfo_blob: Option<&[u8]>,
    ) -> Result<bool, Error> {
        let result: Result<_, _> = try {
            let n = self
                .0
                .connect()?
                .prepare_cached(formatcp!(
                    "INSERT OR IGNORE INTO {TORRENT} ({INFO_HASH}, {INFO}, {METAINFO}) VALUES (?1, ?2, ?3)"
                ))?
                .execute((info_hash.as_ref() as &[u8], info_blob, metainfo_blob))?;
            assert!(n == 0 || n == 1, "n == {n}");
            n == 1
        };
        result.context(SqliteSnafu)
    }

    pub(crate) fn remove(&self, info_hash: InfoHash) -> Result<bool, Error> {
        let result: Result<_, _> = try {
            let n = self
                .0
                .connect()?
                .prepare_cached(formatcp!("DELETE FROM {TORRENT} WHERE {INFO_HASH} = ?1"))?
                .execute([info_hash.as_ref() as &[u8]])?;
            assert!(n == 0 || n == 1, "n == {n}");
            n == 1
        };
        result.context(SqliteSnafu)
    }
}

fn reader_decode<T>(mut data: Bytes) -> T
where
    T: DeserializeOwned + SanityCheck,
{
    let value = match bt_bencode::from_buf_strict::<_, T>(&mut data) {
        Ok(value) => value,
        Err(error) => panic!("metadata corruption: {error}"),
    };

    if let Err(insane) = value.sanity_check() {
        tracing::warn!(%insane, "new(?) metadata sanity check fail");
    }

    if !data.is_empty() {
        panic!(
            "metadata corruption: trailing data: \"{}\"",
            data.escape_ascii(),
        );
    }

    value
}

fn writer_decode<T>(mut data: &[u8]) -> Result<T, Error>
where
    T: DeserializeOwned + SanityCheck,
{
    let value = bt_bencode::from_buf_strict::<_, T>(&mut data).context(BencodeSnafu)?;

    value.sanity_check().context(MetadataInsaneSnafu)?;

    ensure!(
        data.is_empty(),
        MetadataTrailingDataSnafu {
            data: Bytes::copy_from_slice(data),
        },
    );

    Ok(value)
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use bytes::{BufMut, BytesMut};
    use tempfile::NamedTempFile;

    use bt_metainfo::Symptom;

    use crate::testing::{mock_info, mock_metainfo};

    use super::*;

    fn assert_db(db: &MetadataDb, expect: &[InfoHash]) {
        assert_matches!(db.list(), Ok(info_hashes) if info_hashes == expect);
    }

    #[test]
    fn get_metainfo() {
        let expect = mock_metainfo(&mock_info("foo", b"bar", 1, &[]));
        let info_hash = expect.info_hash();

        let temp = NamedTempFile::new().unwrap();
        let db = MetadataDb::open(temp.path().to_path_buf()).unwrap();
        assert_db(&db, &[]);

        for _ in 0..3 {
            assert_matches!(db.get_metainfo(info_hash.clone()), Ok(None));
        }

        assert_matches!(db.insert_metainfo(expect.clone()), Ok(true));
        assert_db(&db, &[info_hash.clone()]);

        for _ in 0..3 {
            assert_matches!(
                db.get_metainfo(info_hash.clone()),
                Ok(Some(metainfo)) if metainfo == expect,
            );
        }
    }

    #[test]
    fn get_metainfo_null() {
        let expect = mock_info("foo", b"bar", 1, &[]);
        let info_hash = InfoHash::digest(&bt_bencode::to_bytes(&expect).unwrap());

        let temp = NamedTempFile::new().unwrap();
        let db = MetadataDb::open(temp.path().to_path_buf()).unwrap();
        assert_matches!(db.insert_info(expect.clone()), Ok(true));
        assert_db(&db, &[info_hash.clone()]);

        for _ in 0..3 {
            assert_matches!(db.get_metainfo(info_hash.clone()), Ok(None));
        }
        assert_matches!(
            db.get_info(info_hash.clone()),
            Ok(Some(info)) if info == expect,
        );
    }

    #[test]
    fn get_info() {
        let expect = mock_info("foo", b"bar", 1, &[]);
        let info_hash = InfoHash::digest(&bt_bencode::to_bytes(&expect).unwrap());

        let temp = NamedTempFile::new().unwrap();
        let db = MetadataDb::open(temp.path().to_path_buf()).unwrap();
        assert_db(&db, &[]);

        for _ in 0..3 {
            assert_matches!(db.get_info(info_hash.clone()), Ok(None));
        }

        assert_matches!(db.insert_info(expect.clone()), Ok(true));
        assert_db(&db, &[info_hash.clone()]);

        for _ in 0..3 {
            assert_matches!(
                db.get_info(info_hash.clone()),
                Ok(Some(info)) if info == expect,
            );
        }
    }

    #[test]
    #[should_panic(expected = "metadata corruption: incomplete bencode data")]
    fn check_metadata_corruption() {
        let info_hash = InfoHash::from([0; 20]);

        let temp = NamedTempFile::new().unwrap();
        let db = MetadataDb::open(temp.path().to_path_buf()).unwrap();
        assert_matches!(db.insert(info_hash.clone(), b"d", None), Ok(true));

        let _ = db.get_info(info_hash);
    }

    #[test]
    #[should_panic(expected = "metadata corruption: trailing data: \"\\xff\"")]
    fn check_metadata_corruption_trailing_data() {
        let mut info_blob = BytesMut::new();
        bt_bencode::to_buf(&mut info_blob, &mock_info("foo", b"bar", 1, &[])).unwrap();
        let info_hash = InfoHash::digest(&info_blob);

        info_blob.put_u8(0xff);

        let temp = NamedTempFile::new().unwrap();
        let db = MetadataDb::open(temp.path().to_path_buf()).unwrap();
        assert_matches!(db.insert(info_hash.clone(), &info_blob, None), Ok(true));

        let _ = db.get_info(info_hash);
    }

    #[test]
    fn get_metainfo_blob() {
        let metainfo = mock_metainfo(&mock_info("foo", b"bar", 1, &[]));
        let info_hash = metainfo.info_hash();
        let expect = bt_bencode::to_bytes(&metainfo).unwrap();

        let temp = NamedTempFile::new().unwrap();
        let db = MetadataDb::open(temp.path().to_path_buf()).unwrap();
        assert_db(&db, &[]);

        for _ in 0..3 {
            assert_matches!(db.get_metainfo_blob(info_hash.clone()), Ok(None));
        }

        assert_matches!(db.insert_metainfo(metainfo.clone()), Ok(true));
        assert_db(&db, &[info_hash.clone()]);

        for _ in 0..3 {
            assert_matches!(
                db.get_metainfo_blob(info_hash.clone()),
                Ok(Some(metainfo_blob)) if metainfo_blob == expect,
            );
        }
    }

    #[test]
    fn get_metainfo_blob_null() {
        let info = mock_info("foo", b"bar", 1, &[]);
        let expect = bt_bencode::to_bytes(&info).unwrap();
        let info_hash = InfoHash::digest(&expect);

        let temp = NamedTempFile::new().unwrap();
        let db = MetadataDb::open(temp.path().to_path_buf()).unwrap();
        assert_matches!(db.insert_info(info), Ok(true));
        assert_db(&db, &[info_hash.clone()]);

        for _ in 0..3 {
            assert_matches!(db.get_metainfo_blob(info_hash.clone()), Ok(None));
        }
        assert_matches!(
            db.get_info_blob(info_hash.clone()),
            Ok(Some(info_blob)) if info_blob == expect,
        );
    }

    #[test]
    fn get_info_blob() {
        let metainfo = mock_metainfo(&mock_info("foo", b"bar", 1, &[]));
        let info_hash = metainfo.info_hash();
        let expect = Bytes::copy_from_slice(metainfo.info_blob());

        let temp = NamedTempFile::new().unwrap();
        let db = MetadataDb::open(temp.path().to_path_buf()).unwrap();
        assert_db(&db, &[]);

        for _ in 0..3 {
            assert_matches!(db.get_info_blob(info_hash.clone()), Ok(None));
        }

        assert_matches!(db.insert_metainfo(metainfo), Ok(true));
        assert_db(&db, &[info_hash.clone()]);

        for _ in 0..3 {
            assert_matches!(
                db.get_info_blob(info_hash.clone()),
                Ok(Some(info_blob)) if info_blob == expect,
            );
        }
    }

    #[test]
    fn insert_metainfo() {
        let metainfo = mock_metainfo(&mock_info("foo", b"bar", 1, &[]));
        let info_hash = metainfo.info_hash();

        let temp = NamedTempFile::new().unwrap();
        let db = MetadataDb::open(temp.path().to_path_buf()).unwrap();
        assert_db(&db, &[]);

        assert_matches!(db.insert_metainfo(metainfo.clone()), Ok(true));
        assert_db(&db, &[info_hash.clone()]);

        assert_matches!(db.insert_metainfo(metainfo), Ok(false));
        assert_db(&db, &[info_hash.clone()]);

        assert_matches!(
            db.insert_metainfo(mock_metainfo(&mock_info("foo", b"", 1, &[]))),
            Err(Error::MetadataInsane { source }) if source.symptoms() == &[Symptom::PiecesEmpty],
        );
        assert_db(&db, &[info_hash.clone()]);
    }

    #[test]
    fn insert_info() {
        let info = mock_info("foo", b"bar", 1, &[]);
        let info_hash = InfoHash::digest(&bt_bencode::to_bytes(&info).unwrap());

        let temp = NamedTempFile::new().unwrap();
        let db = MetadataDb::open(temp.path().to_path_buf()).unwrap();
        assert_db(&db, &[]);

        assert_matches!(db.insert_info(info.clone()), Ok(true));
        assert_db(&db, &[info_hash.clone()]);

        assert_matches!(db.insert_info(info), Ok(false));
        assert_db(&db, &[info_hash.clone()]);

        assert_matches!(
            db.insert_info(mock_info("foo", b"", 1, &[])),
            Err(Error::MetadataInsane { source }) if source.symptoms() == &[Symptom::PiecesEmpty],
        );
        assert_db(&db, &[info_hash.clone()]);
    }

    #[test]
    fn insert_metainfo_blob() {
        let metainfo = mock_metainfo(&mock_info("foo", b"bar", 1, &[]));
        let info_hash = metainfo.info_hash();
        let mut metainfo_blob = BytesMut::new();
        bt_bencode::to_buf(&mut metainfo_blob, &metainfo).unwrap();

        let temp = NamedTempFile::new().unwrap();
        let db = MetadataDb::open(temp.path().to_path_buf()).unwrap();
        assert_db(&db, &[]);

        assert_matches!(db.insert_metainfo_blob(&metainfo_blob), Ok(true));
        assert_db(&db, &[info_hash.clone()]);

        assert_matches!(db.insert_metainfo_blob(&metainfo_blob), Ok(false));
        assert_db(&db, &[info_hash.clone()]);

        metainfo_blob.put_u8(1);
        assert_matches!(
            db.insert_metainfo_blob(&metainfo_blob),
            Err(Error::MetadataTrailingData { data }) if *data == *b"\x01",
        );
        assert_db(&db, &[info_hash.clone()]);

        let metainfo_blob =
            bt_bencode::to_bytes(&mock_metainfo(&mock_info("foo", b"", 1, &[]))).unwrap();
        assert_matches!(
            db.insert_metainfo_blob(&metainfo_blob),
            Err(Error::MetadataInsane { source }) if source.symptoms() == &[Symptom::PiecesEmpty],
        );
        assert_db(&db, &[info_hash.clone()]);
    }

    #[test]
    fn insert_info_blob() {
        let mut info_blob = BytesMut::new();
        bt_bencode::to_buf(&mut info_blob, &mock_info("foo", b"bar", 1, &[])).unwrap();
        let info_hash = InfoHash::digest(&info_blob);

        let temp = NamedTempFile::new().unwrap();
        let db = MetadataDb::open(temp.path().to_path_buf()).unwrap();
        assert_db(&db, &[]);

        assert_matches!(db.insert_info_blob(&info_blob), Ok(true));
        assert_db(&db, &[info_hash.clone()]);

        assert_matches!(db.insert_info_blob(&info_blob), Ok(false));
        assert_db(&db, &[info_hash.clone()]);

        info_blob.put_u8(2);
        assert_matches!(
            db.insert_info_blob(&info_blob),
            Err(Error::MetadataTrailingData { data }) if *data == *b"\x02",
        );
        assert_db(&db, &[info_hash.clone()]);

        let info_blob = bt_bencode::to_bytes(&mock_info("foo", b"", 1, &[])).unwrap();
        assert_matches!(
            db.insert_info_blob(&info_blob),
            Err(Error::MetadataInsane { source }) if source.symptoms() == &[Symptom::PiecesEmpty],
        );
        assert_db(&db, &[info_hash.clone()]);
    }

    #[test]
    fn remove() {
        let metainfo = mock_metainfo(&mock_info("foo", b"bar", 1, &[]));
        let info_hash = metainfo.info_hash();

        let temp = NamedTempFile::new().unwrap();
        let db = MetadataDb::open(temp.path().to_path_buf()).unwrap();
        assert_db(&db, &[]);

        assert_matches!(db.insert_metainfo(metainfo), Ok(true));
        assert_db(&db, &[info_hash.clone()]);

        assert_matches!(db.remove(info_hash.clone()), Ok(true));
        assert_db(&db, &[]);

        assert_matches!(db.remove(info_hash.clone()), Ok(false));
        assert_db(&db, &[]);
    }
}
