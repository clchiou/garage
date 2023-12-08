use std::ops::RangeInclusive;

use snafu::prelude::*;

use crate::{Error, Info, InsaneSnafu, Metainfo, Mode};

const PIECE_LENGTH_RANGE: RangeInclusive<u64> = 512..=(2 * MB);
const MB: u64 = 1 << 20;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Insanity {
    // Field: announce and announce_list
    EmptyAnnounceList,
    EmptyAnnounceUrl,

    // Field: info
    //
    // TODO: Consider classifying `piece_length` that is not a power of 2 as insane.
    EmptyName,
    EmptyFiles,
    EmptyPath,
    EmptyPathComponent,
    EmptyPieces,
    #[snafu(display("expect length in {range:?}: {length}"))]
    InvalidLength {
        length: u64,
        range: RangeInclusive<u64>,
    },
    #[snafu(display("expect piece_length in {PIECE_LENGTH_RANGE:?}: {piece_length}"))]
    InvalidPieceLength {
        piece_length: u64,
    },
}

impl<'a> Metainfo<'a> {
    pub(crate) fn sanity_check(&self) -> Result<(), Error> {
        let symptoms: Vec<Insanity> = self
            .iter_symptoms()
            .chain(self.info.iter_symptoms())
            .collect();
        ensure!(symptoms.is_empty(), InsaneSnafu { symptoms });
        Ok(())
    }

    fn iter_symptoms(&self) -> impl Iterator<Item = Insanity> + '_ {
        self.check_empty_announce_url()
            .into_iter()
            .chain(self.check_empty_announce_list())
    }

    fn check_empty_announce_url(&self) -> Option<Insanity> {
        if let Some(url) = &self.announce {
            if url.is_empty() {
                return Some(Insanity::EmptyAnnounceUrl);
            }
        }
        if let Some(list_of_list) = &self.announce_list {
            if list_of_list
                .iter()
                .any(|list| list.iter().any(|url| url.is_empty()))
            {
                return Some(Insanity::EmptyAnnounceUrl);
            }
        }
        None
    }

    fn check_empty_announce_list(&self) -> Option<Insanity> {
        if let Some(list_of_list) = &self.announce_list {
            if list_of_list.is_empty() || list_of_list.iter().any(|list| list.is_empty()) {
                return Some(Insanity::EmptyAnnounceList);
            }
        }
        None
    }
}

impl<'a> Info<'a> {
    pub(crate) fn sanity_check(&self) -> Result<(), Error> {
        let symptoms: Vec<Insanity> = self.iter_symptoms().collect();
        ensure!(symptoms.is_empty(), InsaneSnafu { symptoms });
        Ok(())
    }

    fn iter_symptoms(&self) -> impl Iterator<Item = Insanity> + '_ {
        self.check_empty_name()
            .into_iter()
            .chain(self.check_files())
            .chain(self.check_pieces())
            .chain(self.check_invalid_piece_length())
    }

    fn check_empty_name(&self) -> Option<Insanity> {
        if self.name.is_empty() {
            Some(Insanity::EmptyName)
        } else {
            None
        }
    }

    fn check_files(&self) -> Option<Insanity> {
        if let Mode::MultiFile { files } = &self.mode {
            if files.is_empty() {
                return Some(Insanity::EmptyFiles);
            }
            for file in files.iter() {
                if file.path.is_empty() {
                    return Some(Insanity::EmptyPath);
                } else if file.path.iter().any(|c| c.is_empty()) {
                    return Some(Insanity::EmptyPathComponent);
                }
            }
        }
        None
    }

    fn check_pieces(&self) -> Option<Insanity> {
        if self.pieces.is_empty() {
            return Some(Insanity::EmptyPieces);
        }
        let length = self.length();
        let num_pieces = self.pieces.len() as u64;
        let range = (num_pieces - 1) * self.piece_length + 1..=num_pieces * self.piece_length;
        if range.contains(&length) {
            None
        } else {
            Some(Insanity::InvalidLength { length, range })
        }
    }

    fn check_invalid_piece_length(&self) -> Option<Insanity> {
        if PIECE_LENGTH_RANGE.contains(&self.piece_length) {
            None
        } else {
            Some(Insanity::InvalidPieceLength {
                piece_length: self.piece_length,
            })
        }
    }
}

#[cfg(test)]
mod tests {
    use crate::File;

    use super::*;

    #[test]
    fn metainfo() {
        let mut metainfo = Metainfo::new_dummy();
        assert_eq!(metainfo.iter_symptoms().collect::<Vec<Insanity>>(), vec![]);
        assert_eq!(
            metainfo.sanity_check(),
            Err(Error::Insane {
                symptoms: vec![
                    Insanity::EmptyName,
                    Insanity::EmptyPieces,
                    Insanity::InvalidPieceLength { piece_length: 0 },
                ],
            }),
        );

        metainfo.announce = Some("");
        metainfo.announce_list = Some(vec![]);
        assert_eq!(
            metainfo.iter_symptoms().collect::<Vec<Insanity>>(),
            vec![Insanity::EmptyAnnounceUrl, Insanity::EmptyAnnounceList],
        );
        assert_eq!(
            metainfo.sanity_check(),
            Err(Error::Insane {
                symptoms: vec![
                    Insanity::EmptyAnnounceUrl,
                    Insanity::EmptyAnnounceList,
                    Insanity::EmptyName,
                    Insanity::EmptyPieces,
                    Insanity::InvalidPieceLength { piece_length: 0 },
                ],
            }),
        );

        metainfo.announce = Some("foo");
        metainfo.announce_list = Some(vec![vec![]]);
        metainfo.info.name = "bar";
        metainfo.info.mode = Mode::SingleFile {
            length: 1,
            md5sum: None,
        };
        metainfo.info.piece_length = 512;
        metainfo.info.pieces = vec![b""];
        assert_eq!(
            metainfo.iter_symptoms().collect::<Vec<Insanity>>(),
            vec![Insanity::EmptyAnnounceList],
        );
        assert_eq!(
            metainfo.sanity_check(),
            Err(Error::Insane {
                symptoms: vec![Insanity::EmptyAnnounceList],
            }),
        );

        metainfo.announce_list = Some(vec![vec![""]]);
        assert_eq!(
            metainfo.iter_symptoms().collect::<Vec<Insanity>>(),
            vec![Insanity::EmptyAnnounceUrl],
        );
        assert_eq!(
            metainfo.sanity_check(),
            Err(Error::Insane {
                symptoms: vec![Insanity::EmptyAnnounceUrl],
            }),
        );

        metainfo.announce_list = Some(vec![vec!["spam"]]);
        assert_eq!(metainfo.iter_symptoms().collect::<Vec<Insanity>>(), vec![]);
        assert_eq!(metainfo.sanity_check(), Ok(()));
    }

    #[test]
    fn info() {
        let mut info = Info::new_dummy();
        assert_eq!(
            info.sanity_check(),
            Err(Error::Insane {
                symptoms: vec![
                    Insanity::EmptyName,
                    Insanity::EmptyPieces,
                    Insanity::InvalidPieceLength { piece_length: 0 },
                ],
            }),
        );

        info.name = "foo";
        info.mode = Mode::MultiFile { files: vec![] };
        info.pieces = vec![b"".as_slice()];
        info.piece_length = 512;
        assert_eq!(
            info.sanity_check(),
            Err(Error::Insane {
                symptoms: vec![
                    Insanity::EmptyFiles,
                    Insanity::InvalidLength {
                        length: 0,
                        range: 1..=512,
                    },
                ],
            }),
        );

        let mut file = File::new_dummy();
        file.length = 513;
        info.mode = Mode::MultiFile { files: vec![file] };
        assert_eq!(
            info.sanity_check(),
            Err(Error::Insane {
                symptoms: vec![
                    Insanity::EmptyPath,
                    Insanity::InvalidLength {
                        length: 513,
                        range: 1..=512,
                    },
                ],
            }),
        );

        let mut file = File::new_dummy();
        file.path = vec![""];
        file.length = 100;
        info.mode = Mode::MultiFile { files: vec![file] };
        assert_eq!(
            info.sanity_check(),
            Err(Error::Insane {
                symptoms: vec![Insanity::EmptyPathComponent],
            }),
        );

        let mut file = File::new_dummy();
        file.path = vec!["foo"];
        file.length = 100;
        info.mode = Mode::MultiFile { files: vec![file] };
        assert_eq!(info.sanity_check(), Ok(()));
    }
}
