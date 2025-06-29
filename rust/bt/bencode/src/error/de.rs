use serde::de;

pub trait Error: de::Error + From<super::Error> {
    fn is_eof(&self) -> bool;

    fn is_incomplete(&self) -> bool;

    fn is_strict(&self) -> bool;
}
