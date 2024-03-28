use std::io::{Error, RawOsError};
use std::path::Path;

use bytes::Bytes;
use xattr::{self, SUPPORTED_PLATFORM};

// We store blob key and metadata in extended attributes.
#[allow(clippy::assertions_on_constants)]
const _: () = assert!(SUPPORTED_PLATFORM);

const XATTR_NAME_KEY: &str = "user.ddcache.key";
const XATTR_NAME_METADATA: &str = "user.ddcache.metadata";

// TODO: For some reason, `std::io::ErrorKind` does not define `ENODATA`.
const ENODATA: RawOsError = 61;

pub(crate) fn read_key_blocking(blob: &Path) -> Result<Option<Bytes>, Error> {
    Ok(xattr::get(blob, XATTR_NAME_KEY)?.map(Bytes::from))
}

pub(crate) fn write_key_blocking(blob: &Path, key: Bytes) -> Result<(), Error> {
    xattr::set(blob, XATTR_NAME_KEY, &key)
}

pub(crate) fn read_metadata(blob: &Path) -> Result<Option<Bytes>, Error> {
    Ok(xattr::get(blob, XATTR_NAME_METADATA)?.map(Bytes::from))
}

pub(crate) fn write_metadata(blob: &Path, metadata: Bytes) -> Result<(), Error> {
    xattr::set(blob, XATTR_NAME_METADATA, &metadata)
}

pub(crate) fn remove_metadata(blob: &Path) -> Result<(), Error> {
    match xattr::remove(blob, XATTR_NAME_METADATA) {
        Err(error) if error.raw_os_error() == Some(ENODATA) => Ok(()),
        result => result,
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::fs;
    use std::io::ErrorKind;

    use tempfile;

    use super::*;

    #[test]
    fn key() -> Result<(), Error> {
        let tempdir = tempfile::tempdir()?;
        let path = tempdir.path().join("foo");
        assert_matches!(
            read_key_blocking(&path),
            Err(error) if error.kind() == ErrorKind::NotFound,
        );

        fs::write(&path, b"")?;
        assert_eq!(read_key_blocking(&path)?, None);

        let testdata = Bytes::from_static(b"Hello, World!");
        write_key_blocking(&path, testdata.clone())?;
        assert_eq!(read_key_blocking(&path)?, Some(testdata));

        Ok(())
    }

    #[test]
    fn metadata() -> Result<(), Error> {
        let tempdir = tempfile::tempdir()?;
        let path = tempdir.path().join("foo");
        assert_matches!(
            read_metadata(&path),
            Err(error) if error.kind() == ErrorKind::NotFound,
        );

        fs::write(&path, b"")?;
        assert_eq!(read_metadata(&path)?, None);

        let testdata = Bytes::from_static(b"Hello, World!");
        write_metadata(&path, testdata.clone())?;
        assert_eq!(read_metadata(&path)?, Some(testdata));

        remove_metadata(&path)?;
        assert_eq!(read_metadata(&path)?, None);

        Ok(())
    }
}
