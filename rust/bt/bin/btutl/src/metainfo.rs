use std::io::{self, Error, Read, Write};

use bytes::Bytes;
use clap::{Args, Subcommand};

use bt_metainfo::SanityCheck;

#[derive(Args, Debug)]
#[command(about = "Read information from metainfo")]
pub(crate) struct MetainfoCommand {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    #[command(about = "Extract info as a binary blob")]
    InfoBlob,
    #[command(about = "Print info hash")]
    InfoHash,
    #[command(about = "Print the metainfo")]
    Debug,
}

impl MetainfoCommand {
    pub(crate) fn run(&self) -> Result<(), Error> {
        let mut buffer = Vec::new();
        io::stdin().read_to_end(&mut buffer)?;
        let mut buffer = Bytes::from(buffer);

        // The `info` dictionary must be strict.
        let metainfo = bt_bencode::from_buf_strict::<_, bt_metainfo::Metainfo>(&mut buffer)
            .map_err(Error::other)?;

        if !buffer.is_empty() {
            return Err(Error::other(format!(
                "trailing data: \"{}\"",
                buffer.escape_ascii(),
            )));
        }

        metainfo.sanity_check().map_err(Error::other)?;

        let mut writer = io::stdout();
        match self.command {
            Command::InfoBlob => writer.write_all(metainfo.info_blob()),
            Command::InfoHash => writeln!(writer, "{}", metainfo.info_hash()),
            Command::Debug => writeln!(writer, "{metainfo:#?}"),
        }
    }
}
