use std::convert::Infallible;

use bittorrent_bencode::serde as serde_bencode;

use crate::{Info, Metainfo};

impl<'a> TryFrom<&'a [u8]> for Metainfo<'a> {
    type Error = serde_bencode::Error;

    fn try_from(buffer: &'a [u8]) -> Result<Self, Self::Error> {
        serde_bencode::from_bytes(buffer)
    }
}

impl<'a> TryFrom<&'a [u8]> for Info<'a> {
    type Error = serde_bencode::Error;

    fn try_from(buffer: &'a [u8]) -> Result<Self, Self::Error> {
        serde_bencode::from_bytes(buffer)
    }
}

impl<'a> TryFrom<Metainfo<'a>> for Info<'a> {
    type Error = Infallible;

    fn try_from(metainfo: Metainfo<'a>) -> Result<Self, Self::Error> {
        Ok(metainfo.info)
    }
}

#[cfg(test)]
mod tests {
    use bytes::Bytes;

    use crate::{InfoOwner, MetainfoOwner, Mode};

    use super::*;

    #[test]
    fn owner() {
        let mut expect = Metainfo::new_dummy();
        expect.announce_list = Some(vec![vec!["spam"]]);
        expect.info.name = "bar";
        expect.info.mode = Mode::SingleFile {
            length: 1,
            md5sum: None,
        };
        expect.info.piece_length = 512;
        expect.info.pieces = vec![b"0123456789abcdef0123"];

        let testdata = serde_bencode::to_bytes(&expect).unwrap().freeze();
        let metainfo_owner = MetainfoOwner::try_from(testdata.clone()).unwrap();
        assert_eq!(metainfo_owner.deref(), &expect);
        assert_eq!(MetainfoOwner::as_slice(&metainfo_owner), &testdata);

        let testdata = serde_bencode::to_bytes(&expect.info).unwrap().freeze();
        let info_owner = InfoOwner::try_from(testdata.clone()).unwrap();
        assert_eq!(info_owner.deref(), &expect.info);
        assert_eq!(info_owner.deref().raw_info, &testdata);
        assert_eq!(InfoOwner::as_slice(&info_owner), &testdata);

        let info_owner: InfoOwner<Bytes> = metainfo_owner.try_into().unwrap();
        assert_eq!(info_owner.deref(), &expect.info);
        assert_eq!(info_owner.deref().raw_info, &testdata);
        // NOTE: `impl TryFrom<MetainfoOwner> for InfoOwner` does **not** align the raw buffer with
        // the info part.  You must avoid using the raw buffer.
        assert_ne!(InfoOwner::as_slice(&info_owner), &testdata);
    }
}
