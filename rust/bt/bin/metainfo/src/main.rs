use std::error;
use std::io::{self, Read, Write};

use bytes::Bytes;
use clap::{Parser, Subcommand};

use bt_metainfo::SanityCheck;

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
        let mut buffer = Vec::new();
        io::stdin().read_to_end(&mut buffer)?;
        let mut buffer = Bytes::from(buffer);

        // The `info` dictionary must be strict.
        let metainfo = bt_bencode::from_buf_strict::<_, bt_metainfo::Metainfo>(&mut buffer)?;

        if !buffer.is_empty() {
            return Err(std::format!("trailing data: \"{}\"", buffer.escape_ascii()).into());
        }

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
