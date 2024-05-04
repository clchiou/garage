use std::io::Error;
use std::path::Path;

use bytes::Bytes;
use capnp::message;
use capnp::serialize;
use chrono::{TimeZone, Utc};
use xattr::{self, SUPPORTED_PLATFORM};

use crate::storage_capnp::blob_metadata;
use crate::Timestamp;

// Given our use case, it seems more efficient to use a shareable type `Bytes` than a `capnp`
// reader.
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct BlobMetadata {
    pub(crate) key: Bytes,
    pub(crate) metadata: Option<Bytes>,
    pub(crate) size: u64,
    pub(crate) expire_at: Option<Timestamp>,
}

// We store blob metadata in an extended attribute.
#[allow(clippy::assertions_on_constants)]
const _: () = assert!(SUPPORTED_PLATFORM);

const XATTR_NAME_METADATA: &str = "user.ddcache.metadata";

impl BlobMetadata {
    pub(crate) fn read(blob: &Path) -> Result<Self, Error> {
        let size = blob.metadata()?.len();

        let blob_metadata = xattr::get(blob, XATTR_NAME_METADATA)?
            .ok_or_else(|| Error::other(format!("expect ddcache metadata: {}", blob.display())))?;

        let blob_metadata: Result<_, capnp::Error> = try {
            let blob_metadata = serialize::read_message_from_flat_slice(
                &mut blob_metadata.as_slice(),
                Default::default(),
            )?;
            let blob_metadata = blob_metadata.get_root::<blob_metadata::Reader>()?;

            let key = blob_metadata.get_key()?;
            if key.is_empty() {
                return Err(Error::other(format!(
                    "expect non-empty ddcache key: {:?}",
                    blob_metadata,
                )));
            }
            let key = Bytes::copy_from_slice(key);

            let metadata = blob_metadata.get_metadata()?;
            let metadata = (!metadata.is_empty()).then(|| Bytes::copy_from_slice(metadata));

            let expire_at = blob_metadata.get_expire_at();
            let expire_at = (expire_at != 0)
                .then(|| {
                    i64::try_from(expire_at)
                        .ok()
                        .and_then(|t| Utc.timestamp_opt(t, 0).single())
                        .ok_or_else(|| Error::other(format!("invalid timestamp: {}", expire_at)))
                })
                .transpose()?;

            Self {
                key,
                metadata,
                size,
                expire_at,
            }
        };
        blob_metadata.map_err(Error::other)
    }

    pub(crate) fn new(key: Bytes) -> Self {
        assert!(!key.is_empty());
        Self {
            key,
            metadata: None,
            size: 0,
            expire_at: None,
        }
    }

    pub(crate) fn is_expired(&self, now: Timestamp) -> bool {
        self.expire_at.map_or(false, |expire_at| expire_at <= now)
    }

    pub(crate) fn encode(&self) -> Bytes {
        let mut builder = message::Builder::new_default();
        let mut blob_metadata = builder.init_root::<blob_metadata::Builder>();
        blob_metadata.set_key(&self.key);
        if let Some(metadata) = self.metadata.as_ref() {
            blob_metadata.set_metadata(metadata);
        }
        blob_metadata.set_expire_at(
            self.expire_at
                .map_or(0, |t| t.timestamp().try_into().unwrap()),
        );
        serialize::write_message_to_words(&builder).into()
    }

    pub(crate) fn write(&self, blob: &Path) -> Result<(), Error> {
        xattr::set(blob, XATTR_NAME_METADATA, &self.encode())
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl BlobMetadata {
        pub(crate) const fn new_mock(
            key: &'static [u8],
            metadata: Option<&'static [u8]>,
            size: u64,
        ) -> Self {
            assert!(!key.is_empty());
            Self {
                key: Bytes::from_static(key),
                metadata: match metadata {
                    Some(metadata) => Some(Bytes::from_static(metadata)),
                    None => None,
                },
                size,
                expire_at: None,
            }
        }
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
    fn blob_metadata() -> Result<(), Error> {
        let tempdir = tempfile::tempdir()?;
        let path = tempdir.path().join("foo");
        assert_matches!(
            BlobMetadata::read(&path),
            Err(error) if error.kind() == ErrorKind::NotFound,
        );

        fs::write(&path, b"foo bar")?;
        assert_matches!(
            BlobMetadata::read(&path),
            Err(error) if error.to_string().starts_with("expect ddcache metadata: "),
        );

        BlobMetadata::new(Bytes::from_static(b"hello")).write(&path)?;
        let blob_metadata = BlobMetadata::read(&path)?;
        assert_eq!(blob_metadata.size, 7);
        assert_eq!(blob_metadata.key, b"hello".as_slice());
        assert_eq!(blob_metadata.metadata, None);
        assert_eq!(blob_metadata.expire_at, None);

        Ok(())
    }

    #[test]
    fn expire_at() {
        let t1 = Utc.timestamp_opt(1, 0).single().unwrap();
        let t2 = Utc.timestamp_opt(2, 0).single().unwrap();
        let t3 = Utc.timestamp_opt(3, 0).single().unwrap();

        let mut metadata = BlobMetadata::new(Bytes::from_static(b"hello"));
        assert_eq!(metadata.expire_at, None);
        assert_eq!(metadata.is_expired(t1), false);
        assert_eq!(metadata.is_expired(t2), false);
        assert_eq!(metadata.is_expired(t3), false);

        metadata.expire_at = Some(t1);
        assert_eq!(metadata.is_expired(t1), true);
        assert_eq!(metadata.is_expired(t2), true);
        assert_eq!(metadata.is_expired(t3), true);

        metadata.expire_at = Some(t2);
        assert_eq!(metadata.is_expired(t1), false);
        assert_eq!(metadata.is_expired(t2), true);
        assert_eq!(metadata.is_expired(t3), true);

        metadata.expire_at = Some(t3);
        assert_eq!(metadata.is_expired(t1), false);
        assert_eq!(metadata.is_expired(t2), false);
        assert_eq!(metadata.is_expired(t3), true);
    }
}
