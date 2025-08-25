use std::fmt::Debug;
use std::io::{Error, Write};

use clap::ValueEnum;
use serde::Serialize;

#[derive(Clone, Copy, Debug, Eq, PartialEq, ValueEnum)]
pub(crate) enum Format {
    Debug,
    Json,
    Yaml,
}

impl Format {
    pub(crate) fn write<T, W>(&self, value: T, mut writer: W) -> Result<(), Error>
    where
        T: Debug + Serialize,
        W: Write,
    {
        match self {
            Self::Debug => writeln!(writer, "{value:#?}"),
            Self::Json => Ok(serde_json::to_writer_pretty(writer, &value)?),
            Self::Yaml => serde_yaml::to_writer(writer, &value).map_err(Error::other),
        }
    }
}
