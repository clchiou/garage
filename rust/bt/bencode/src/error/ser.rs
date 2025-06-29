use serde::ser;

pub trait Error = ser::Error + From<super::Error>;
