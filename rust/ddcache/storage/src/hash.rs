use std::fs::DirEntry;
use std::io::Error;
use std::path::{Path, PathBuf};
use std::str;

use fasthash::city;
use lazy_regex::regex;

use g1_base::fmt::{DebugExt, Hex};
use g1_base::str::StrExt;

/// Hash of a blob key
///
/// It is 1:1 mapped to a blob path.
#[derive(Clone, Copy, DebugExt, Eq, Hash, PartialEq)]
pub(crate) struct KeyHash(
    // We do not wrap the array in `Arc` here because it seems that the overhead of `Arc` is
    // greater than simply copying the 128-bit array.
    #[debug(with = Hex)] [u8; KEY_HASH_SIZE],
);

// 128 bits appear to be large enough to have a negligible collision rate and are supported by many
// popular non-cryptographic hash functions.
const KEY_HASH_SIZE: usize = 16;

/// Matches and extracts a blob directory path.
pub(crate) fn match_blob_dir(blob_dir: &DirEntry) -> Result<Option<PathBuf>, Error> {
    if !blob_dir.file_type()?.is_dir() {
        return Ok(None);
    }
    let path = blob_dir.path();
    Ok(try {
        regex!(r"^[0-9a-f]{2}$") // Use only lowercase letters (see `to_hex` below).
            .is_match(path.file_name()?.to_str()?)
            .then_some(path)?
    })
}

/// Matches and extracts a blob path.
pub(crate) fn match_blob(blob: &DirEntry) -> Result<Option<PathBuf>, Error> {
    if !blob.file_type()?.is_file() {
        return Ok(None);
    }
    let path = blob.path();
    Ok(try {
        regex!(r"^[0-9a-f]{30}$") // Use only lowercase letters (see `to_hex` below).
            .is_match(path.file_name()?.to_str()?)
            .then_some(path)?
    })
}

impl KeyHash {
    pub(crate) fn new<K: AsRef<[u8]>>(key: K) -> Self {
        // CityHash seems to be a reasonable choice.
        Self(city::hash128(key).to_be_bytes())
    }

    pub(crate) fn from_path(blob: &Path) -> Self {
        let blob_dir = to_file_name(blob.parent().unwrap());
        let blob = to_file_name(blob);
        assert_eq!(blob_dir.len(), 2);
        assert_eq!(blob.len(), (KEY_HASH_SIZE - 1) * 2);

        let mut hash = [0; KEY_HASH_SIZE];
        from_hex(&mut hash[..1], blob_dir);
        from_hex(&mut hash[1..], blob);
        Self(hash)
    }

    pub(crate) fn to_path(self, dir: &Path) -> PathBuf {
        let mut path = dir.to_path_buf();
        let mut buf = [0; KEY_HASH_SIZE * 2];
        let hex = to_hex(self.0.as_slice(), buf.as_mut_slice());
        path.push(Path::new(&hex[..2]));
        path.push(Path::new(&hex[2..]));
        path
    }
}

fn to_file_name(path: &Path) -> &str {
    path.file_name().unwrap().to_str().unwrap()
}

fn from_hex(bytes: &mut [u8], hex: &str) {
    assert_eq!(bytes.len() * 2, hex.len());
    for (b, byte_str) in bytes.iter_mut().zip(hex.chunks(2)) {
        *b = u8::from_str_radix(byte_str, 16).unwrap();
    }
}

fn to_hex<'a>(bytes: &[u8], hex: &'a mut [u8]) -> &'a str {
    const HEX: &[u8] = b"0123456789abcdef";
    assert_eq!(bytes.len() * 2, hex.len());
    for (i, b) in bytes.iter().copied().enumerate() {
        hex[i * 2] = HEX[usize::from((b & 0xf0) >> 4)];
        hex[i * 2 + 1] = HEX[usize::from(b & 0x0f)];
    }
    unsafe { str::from_utf8_unchecked(hex) }
}

#[cfg(test)]
mod tests {
    use std::fs;

    use tempfile;

    use super::*;

    fn scalar<T, I: Iterator<Item = T>>(mut iter: I) -> T {
        iter.next().unwrap()
    }

    #[test]
    fn test_match_blob_dir() -> Result<(), Error> {
        let tempdir = tempfile::tempdir()?;
        for (file_name, expect) in [
            ("00", true),
            ("10", true),
            ("0a", true),
            ("f0", true),
            ("FF", false),
            ("000", false),
            ("0", false),
        ] {
            let path = tempdir.path().join(file_name);

            fs::create_dir(&path)?;
            assert_eq!(
                match_blob_dir(&scalar(tempdir.path().read_dir()?)?)?,
                expect.then_some(path.clone()),
            );
            fs::remove_dir(&path)?;

            fs::write(&path, b"")?;
            assert_eq!(match_blob_dir(&scalar(tempdir.path().read_dir()?)?)?, None);
            fs::remove_file(&path)?;
        }
        Ok(())
    }

    #[test]
    fn test_match_blob() -> Result<(), Error> {
        let tempdir = tempfile::tempdir()?;
        for (file_name, expect) in [
            ("000000000000000000000000000000", true),
            ("000000000000000000000000000010", true),
            ("000000000000000000000000000a00", true),
            ("00000000000000000000000000f000", true),
            ("00000000000000000000000000000F", false),
            ("0000000000000000000000000000000", false),
            ("00000000000000000000000000000", false),
        ] {
            let path = tempdir.path().join(file_name);

            fs::create_dir(&path)?;
            assert_eq!(match_blob(&scalar(tempdir.path().read_dir()?)?)?, None);
            fs::remove_dir(&path)?;

            fs::write(&path, b"")?;
            assert_eq!(
                match_blob(&scalar(tempdir.path().read_dir()?)?)?,
                expect.then_some(path.clone()),
            );
            fs::remove_file(&path)?;
        }
        Ok(())
    }

    #[test]
    fn hash() {
        // If the hash values seem to be reversed at a 64-bit boundary, it is probably due to the
        // combination of these factors:
        // * CityHash C++ code defines `uint128` as `std::pair<uint64_t, uint64_t>`.
        // * fasthash directly transmutes C++ `uint128` to Rust `u128`.
        // * x64 is little endian.
        // Thus, the first 64-bit element appears in the lower half of `u128`, and the second
        // element appears in the higher half.
        assert_eq!(
            KeyHash::new(b""),
            KeyHash(0x3cb540c392e51e293df09dfc64c09a2bu128.to_be_bytes()),
        );
        assert_eq!(
            KeyHash::new([228]),
            KeyHash(0x74836eeafb7f7102535daa5e388d3a90u128.to_be_bytes()),
        );
        assert_eq!(
            KeyHash::new(b"hello"),
            KeyHash(0xf1881d5ba3f4b5ecbbae8265cd136befu128.to_be_bytes()),
        );

        let dir = Path::new("/some/where");
        for (blob, expect) in [
            (
                Path::new("/some/where/00/000000000000000000000000000000"),
                [0; 16],
            ),
            (
                Path::new("/some/where/00/0102030405060708090a0b0c0d0e0f"),
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
            ),
            (
                Path::new("/some/where/ff/ffffffffffffffffffffffffffffff"),
                [0xff; 16],
            ),
        ] {
            let hash = KeyHash::from_path(blob);
            assert_eq!(hash, KeyHash(expect));
            assert_eq!(hash.to_path(dir), blob.to_path_buf());
        }
    }
}
