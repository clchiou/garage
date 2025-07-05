use std::error;
use std::io::{self, Write};

use clap::{Parser, Subcommand};

#[derive(Debug, Parser)]
struct Metainfo {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    InfoBlob,
    InfoHash,
    Debug,
}

type Error = Box<dyn error::Error>;

impl Metainfo {
    fn execute(&self) -> Result<(), Error> {
        // The `info` dictionary must be strict.
        let Some(metainfo) =
            bt_bencode::from_reader_strict::<_, bt_metainfo::Metainfo>(io::stdin())?
        else {
            return Err(bt_bencode::error::Error::Eof.into());
        };

        metainfo.sanity_check()?;

        let mut writer = io::stdout();
        match self.command {
            Command::InfoBlob => writer.write_all(metainfo.info_blob())?,
            Command::InfoHash => std::writeln!(writer, "{}", metainfo.info_hash())?,
            Command::Debug => std::writeln!(writer, "{metainfo:#?}")?,
        }

        Ok(())
    }
}

fn main() -> Result<(), Error> {
    Metainfo::parse().execute()
}
