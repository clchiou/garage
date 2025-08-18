use std::error;
use std::fmt;

use snafu::prelude::*;

use super::{File, Info, Metainfo, Mode};

pub trait SanityCheck {
    fn sanity_check(&self) -> Result<(), Insane>;
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Insane(Vec<Symptom>);

impl fmt::Display for Insane {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let mut first = true;
        for symptom in self.symptoms() {
            if first {
                std::write!(f, "insane: {symptom}")?;
            } else {
                std::write!(f, " ; {symptom}")?;
            }
            first = false;
        }
        Ok(())
    }
}

impl error::Error for Insane {}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Symptom {
    //
    // `Metainfo`
    //
    #[snafu(display("announce url empty"))]
    AnnounceEmpty,
    #[snafu(display("announce url list empty"))]
    AnnounceListEmpty,

    //
    // `Info`
    //
    #[snafu(display("info name empty"))]
    NameEmpty,
    #[snafu(display("info pieces invalid"))]
    PieceLengthInvalid,
    #[snafu(display("info pieces empty"))]
    PiecesEmpty,
    #[snafu(display("info files empty"))]
    FilesEmpty,

    #[snafu(display("torrent length invalid"))]
    LengthInvalid,

    //
    // `File`
    //
    #[snafu(display("file path empty"))]
    PathEmpty,
}

const PIECE_LENGTH_LIMIT: u64 = 4 * 1024 * 1024;

impl Insane {
    // Note that `Self` is in the `Err` variant.
    fn check(symptoms: Vec<Symptom>) -> Result<(), Self> {
        if symptoms.is_empty() {
            Ok(())
        } else {
            Err(Self(symptoms))
        }
    }

    pub fn symptoms(&self) -> &[Symptom] {
        &self.0
    }
}

impl SanityCheck for Metainfo {
    fn sanity_check(&self) -> Result<(), Insane> {
        let mut symptoms = Vec::new();
        self.collect_into(&mut symptoms);
        Insane::check(symptoms)
    }
}

impl SanityCheck for Info {
    fn sanity_check(&self) -> Result<(), Insane> {
        let mut symptoms = Vec::new();
        self.collect_into(&mut symptoms);
        Insane::check(symptoms)
    }
}

trait CollectInto {
    fn collect_into<E>(&self, symptoms: &mut E)
    where
        E: Extend<Symptom>;
}

impl CollectInto for Metainfo {
    fn collect_into<E>(&self, symptoms: &mut E)
    where
        E: Extend<Symptom>,
    {
        symptoms.extend(self.check_announce_empty());
        symptoms.extend(self.check_announce_list_empty());
        self.info.collect_into(symptoms);
    }
}

impl Metainfo {
    fn check_announce_empty(&self) -> Option<Symptom> {
        self.announce()?
            .is_empty()
            .then_some(Symptom::AnnounceEmpty)
    }

    fn check_announce_list_empty(&self) -> Option<Symptom> {
        let list_of_list = self.announce_list()?;
        (list_of_list.is_empty()
            || list_of_list
                .iter()
                .any(|list| list.is_empty() || list.iter().any(|url| url.is_empty())))
        .then_some(Symptom::AnnounceListEmpty)
    }
}

impl CollectInto for Info {
    fn collect_into<E>(&self, symptoms: &mut E)
    where
        E: Extend<Symptom>,
    {
        symptoms.extend(self.check_name_empty());
        symptoms.extend(self.check_piece_length_invalid());
        symptoms.extend(self.check_pieces_empty());
        symptoms.extend(self.check_files_empty());

        symptoms.extend(self.check_length_invalid());

        if let Mode::Multiple { files } = self.mode() {
            for file in files {
                file.collect_into(symptoms);
            }
        }
    }
}

impl Info {
    fn check_name_empty(&self) -> Option<Symptom> {
        self.name().is_empty().then_some(Symptom::NameEmpty)
    }

    fn check_piece_length_invalid(&self) -> Option<Symptom> {
        let p = self.piece_length();
        (!((1..=PIECE_LENGTH_LIMIT).contains(&p) && (p & (p - 1)) == 0))
            .then_some(Symptom::PieceLengthInvalid)
    }

    fn check_pieces_empty(&self) -> Option<Symptom> {
        self.pieces().is_empty().then_some(Symptom::PiecesEmpty)
    }

    fn check_files_empty(&self) -> Option<Symptom> {
        matches!(self.mode(), Mode::Multiple { files } if files.is_empty())
            .then_some(Symptom::FilesEmpty)
    }

    fn check_length_invalid(&self) -> Option<Symptom> {
        let length = self.length();
        let n = u64::try_from(self.pieces().len()).expect("u64");
        let p = self.piece_length();
        (!match n * p {
            0 => length == 0,
            max => ((n - 1) * p + 1..=max).contains(&length),
        })
        .then_some(Symptom::LengthInvalid)
    }
}

impl CollectInto for File {
    fn collect_into<E>(&self, symptoms: &mut E)
    where
        E: Extend<Symptom>,
    {
        symptoms.extend(self.check_path_empty());
    }
}

impl File {
    fn check_path_empty(&self) -> Option<Symptom> {
        let path = self.path();
        (path.is_empty() || path.iter().any(|comp| comp.is_empty())).then_some(Symptom::PathEmpty)
    }
}

#[cfg(test)]
mod tests {
    use bt_base::PieceHashes;
    use bt_bencode::bencode;

    use super::*;

    macro_rules! replace {
        ($origin:ident => $($field:ident : $value:expr),* $(,)?) => {{
            let mut copy = $origin.clone();
            $(copy.$field = $value;)*
            copy
        }};
    }

    fn s(length: u64) -> Mode {
        Mode::Single {
            length,
            md5sum: None,
        }
    }

    fn m<const N: usize>(files: [File; N]) -> Mode {
        Mode::Multiple {
            files: files.into(),
        }
    }

    fn f<const N: usize>(length: u64, path: [&str; N]) -> File {
        File {
            length,
            path: v(path),
            md5sum: None,
            extra: bencode!({}),
        }
    }

    fn v<const N: usize>(strs: [&str; N]) -> Vec<String> {
        strs.into_iter().map(String::from).collect()
    }

    fn test<T>(testdata: &T, expect: &[Symptom])
    where
        T: CollectInto,
    {
        let mut actual = Vec::new();
        testdata.collect_into(&mut actual);
        assert_eq!(actual, expect);
    }

    #[test]
    fn metainfo() {
        fn test_metainfo(metainfo: &Metainfo, expect: &[Symptom]) {
            test(metainfo, expect);

            if expect.is_empty() {
                assert_eq!(metainfo.sanity_check(), Ok(()));
            } else {
                assert_eq!(metainfo.sanity_check(), Err(Insane(expect.to_vec())));
            }
        }

        let metainfo = bt_bencode::to_bytes(&bencode!({
            b"info": {
                b"name": b"foo",
                b"piece length": 1,
                b"pieces": ([0u8; 20]),
                b"length": 1,
            },
        }))
        .unwrap();
        let metainfo = bt_bencode::from_buf::<_, Metainfo>(metainfo).unwrap();
        test_metainfo(&metainfo, &[]);

        test_metainfo(
            &replace!(metainfo => announce: Some("foo".to_string())),
            &[],
        );
        test_metainfo(
            &replace!(metainfo => announce: Some("".to_string())),
            &[Symptom::AnnounceEmpty],
        );

        test_metainfo(
            &replace!(metainfo => announce_list: Some(vec![v(["foo"])])),
            &[],
        );
        for announce_list in [vec![], vec![v([])], vec![v([""])], vec![v(["foo", ""])]] {
            test_metainfo(
                &replace!(metainfo => announce_list: Some(announce_list)),
                &[Symptom::AnnounceListEmpty],
            );
        }

        let metainfo = bt_bencode::to_bytes(&bencode!({
            b"info": {
                b"name": b"",
                b"piece length": 0,
                b"pieces": b"",
                b"length": 1,
            },
        }))
        .unwrap();
        let metainfo = bt_bencode::from_buf::<_, Metainfo>(metainfo).unwrap();
        test_metainfo(
            &metainfo,
            &[
                Symptom::NameEmpty,
                Symptom::PieceLengthInvalid,
                Symptom::PiecesEmpty,
                Symptom::LengthInvalid,
            ],
        );
    }

    #[test]
    fn info() {
        let info = Info {
            name: "foo".to_string(),
            piece_length: 1,
            pieces: PieceHashes::new([0; 20].into()).unwrap(),
            mode: s(1),
            private: None,
            extra: bencode!({}),
        };
        test(&info, &[]);

        test(
            &replace!(info => name: "".to_string()),
            &[Symptom::NameEmpty],
        );

        for piece_length in [
            0,
            3,
            5,
            7,
            PIECE_LENGTH_LIMIT - 1,
            PIECE_LENGTH_LIMIT + 1,
            PIECE_LENGTH_LIMIT * 2,
        ] {
            test(
                &replace!(info => piece_length: piece_length, mode: s(piece_length)),
                &[Symptom::PieceLengthInvalid],
            );
        }

        test(
            &replace!(info => pieces: PieceHashes::new([].into()).unwrap(), mode: s(0)),
            &[Symptom::PiecesEmpty],
        );

        test(
            &replace!(info => piece_length: 0, mode: m([])),
            &[Symptom::PieceLengthInvalid, Symptom::FilesEmpty],
        );

        //
        // Symptom::LengthInvalid
        //
        test(
            &replace!(info => piece_length: 0),
            &[Symptom::PieceLengthInvalid, Symptom::LengthInvalid],
        );
        test(
            &replace!(info => pieces: PieceHashes::new([].into()).unwrap()),
            &[Symptom::PiecesEmpty, Symptom::LengthInvalid],
        );
        for length in [0, 2, 3, 4] {
            test(
                &replace!(info => mode: s(length)),
                &[Symptom::LengthInvalid],
            );
            test(
                &replace!(info => mode: m([f(length, ["foo"])])),
                &[Symptom::LengthInvalid],
            );
        }
        {
            let info = replace!(
                info =>
                piece_length: 4,
                pieces: PieceHashes::new([0; 60].into()).unwrap(),
            );
            for length in [9, 10, 11, 12] {
                test(&replace!(info => mode: s(length)), &[]);
                test(&replace!(info => mode: m([f(length, ["foo"])])), &[]);
            }
            for length in [0, 1, 2, 7, 8, 13, 14, 15] {
                test(
                    &replace!(info => mode: s(length)),
                    &[Symptom::LengthInvalid],
                );
                test(
                    &replace!(info => mode: m([f(length, ["foo"])])),
                    &[Symptom::LengthInvalid],
                );
            }
        }

        test(
            &replace!(info => mode: m([f(1, [])])),
            &[Symptom::PathEmpty],
        );
    }

    #[test]
    fn file() {
        let file = f(0, ["foo", "bar"]);
        test(&file, &[]);

        for path in [v([]), v([""]), v(["foo", ""])] {
            test(&replace!(file => path: path), &[Symptom::PathEmpty]);
        }
    }
}
