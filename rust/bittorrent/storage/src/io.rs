use std::cmp;
use std::io::Error;
use std::os::fd::AsRawFd;
use std::path::{Component, Path};

use sha1::{Digest, Sha1};
use snafu::prelude::*;
use tokio::{
    fs::{self, File, OpenOptions},
    io::AsyncReadExt,
};

use crate::{error, PieceHash};

#[derive(Debug)]
pub(crate) struct PieceHasher {
    hasher: Sha1,
}

impl PieceHasher {
    pub(crate) fn new() -> Self {
        Self {
            hasher: Sha1::new(),
        }
    }

    /// Updates the hasher with the given file.
    ///
    /// It assumes that the file has been seeked.
    pub(crate) async fn update(&mut self, file: &mut File, mut size: usize) -> Result<(), Error> {
        let mut buffer = [0u8; 4096]; // TODO: What buffer size should we use?
        while size > 0 {
            let buf_size = cmp::min(buffer.len(), size);
            let buf = &mut buffer[..buf_size];
            file.read_exact(buf).await?;
            self.hasher.update(buf);
            size -= buf_size;
        }
        Ok(())
    }

    pub(crate) fn finalize(self) -> PieceHash {
        self.hasher.finalize().into()
    }
}

pub(crate) async fn open(path: &Path, size: u64) -> Result<File, Error> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).await?;
    }
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)
        .await?;
    if size > 0 {
        fallocate(&file, size)?;
    }
    Ok(file)
}

pub(crate) fn expect_dir(path: &Path) -> Result<&Path, error::Error> {
    ensure!(
        path.is_dir(),
        error::ExpectDirectorySnafu {
            path: path.to_path_buf(),
        },
    );
    Ok(path)
}

pub(crate) fn expect_relpath(path_str: &str) -> Result<&Path, error::Error> {
    ensure!(
        !path_str.is_empty(),
        error::ExpectRelpathSnafu {
            path: path_str.to_string(),
        },
    );
    let path = Path::new(path_str);
    ensure!(
        path.components().all(|c| matches!(c, Component::Normal(_))),
        error::ExpectRelpathSnafu {
            path: path_str.to_string(),
        },
    );
    Ok(path)
}

// TODO: Could we turn this into an async function?
fn fallocate(file: &impl AsRawFd, size: u64) -> Result<(), Error> {
    // TODO: `fallocate` is Linux-specific.  Should we use `posix_fallocate` instead?
    if unsafe { libc::fallocate(file.as_raw_fd(), 0, 0, size.try_into().unwrap()) } < 0 {
        return Err(Error::last_os_error());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use hex_literal::hex;
    use tempfile;

    use super::*;

    fn assert_file_size(path: &Path, size: u64) {
        let metadata = path.metadata().unwrap();
        assert!(metadata.is_file());
        assert_eq!(metadata.len(), size);
    }

    #[tokio::test]
    async fn piece_hasher() {
        assert_eq!(
            PieceHasher::new().finalize(),
            hex!("da39a3ee5e6b4b0d3255bfef95601890afd80709"),
        );

        let mut zero = File::open("/dev/zero").await.unwrap();

        let mut hasher = PieceHasher::new();
        hasher.update(&mut zero, 1000).await.unwrap();
        assert_eq!(
            hasher.finalize(),
            hex!("c577f7a37657053275f3e3ecc06ec22e6b909366"),
        );

        let mut hasher = PieceHasher::new();
        hasher.update(&mut zero, 10000).await.unwrap();
        assert_eq!(
            hasher.finalize(),
            hex!("f907b7bf318b79fd6b9da589646f8b1dac77d0c8"),
        );

        let mut hasher = PieceHasher::new();
        hasher.update(&mut zero, 1000).await.unwrap();
        hasher.update(&mut zero, 2000).await.unwrap();
        hasher.update(&mut zero, 3000).await.unwrap();
        hasher.update(&mut zero, 4000).await.unwrap();
        assert_eq!(
            hasher.finalize(),
            hex!("f907b7bf318b79fd6b9da589646f8b1dac77d0c8"),
        );
    }

    #[tokio::test]
    async fn test_open() {
        let tempdir = tempfile::tempdir().unwrap();

        let path = tempdir.path().join("a/b/c");
        let _ = open(&path, 23).await.unwrap();
        assert_file_size(&path, 23);

        let path = tempdir.path().join("d/e/f");
        let _ = open(&path, 0).await.unwrap();
        assert_file_size(&path, 0);
    }

    #[test]
    fn test_expect_dir() {
        assert_eq!(expect_dir(Path::new(".")), Ok(Path::new(".")));
        assert_eq!(
            expect_dir(Path::new("/dev/null")),
            Err(error::Error::ExpectDirectory {
                path: "/dev/null".to_string().into(),
            }),
        );
    }

    #[test]
    fn test_expect_relpath() {
        fn test_err(path_str: &str) {
            assert_eq!(
                expect_relpath(path_str),
                Err(error::Error::ExpectRelpath {
                    path: path_str.to_string(),
                }),
            );
        }

        assert_eq!(expect_relpath(" "), Ok(Path::new(" ")));
        assert_eq!(expect_relpath(" / "), Ok(Path::new(" / ")));
        assert_eq!(expect_relpath("a///b"), Ok(Path::new("a///b")));
        assert_eq!(expect_relpath("a/b/c"), Ok(Path::new("a/b/c")));
        assert_eq!(expect_relpath("a/./b"), Ok(Path::new("a/./b")));
        assert_eq!(expect_relpath("a/b/."), Ok(Path::new("a/b/.")));

        test_err("");
        test_err("/");
        test_err("/a");
        test_err("./a");
        test_err("../a");
        test_err("a/../b");
        test_err("a/b/..");
    }

    #[tokio::test]
    async fn test_fallocate() {
        let file = tempfile::tempfile().unwrap();
        assert_eq!(file.metadata().unwrap().len(), 0);
        fallocate(&file, 42).unwrap();
        assert_eq!(file.metadata().unwrap().len(), 42);

        let tempdir = tempfile::tempdir().unwrap();
        let file = File::open(tempdir.path()).await.unwrap();
        let error = fallocate(&file, 42).unwrap_err();
        assert_eq!(error.to_string(), "Bad file descriptor (os error 9)");
    }
}
