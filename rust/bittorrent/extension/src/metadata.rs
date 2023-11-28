use bittorrent_bencode::own;

use crate::Error;

pub(crate) fn to_metadata_size(size: i64) -> Result<usize, Error> {
    size.try_into()
        .map_err(|_| Error::InvalidMetadataSize { size })
}

pub(crate) fn from_metadata_size(size: usize) -> own::Value {
    i64::try_from(size).unwrap().into()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn metadata_size() {
        assert_eq!(to_metadata_size(0), Ok(0));
        assert_eq!(to_metadata_size(42), Ok(42));
        assert_eq!(
            to_metadata_size(-1),
            Err(Error::InvalidMetadataSize { size: -1 }),
        );

        assert_eq!(from_metadata_size(0), 0.into());
        assert_eq!(from_metadata_size(42), 42.into());
    }
}
