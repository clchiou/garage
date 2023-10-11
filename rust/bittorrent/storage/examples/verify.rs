#![feature(io_error_other)]

use std::io::Error;
use std::path::PathBuf;

use clap::{Parser, ValueEnum};
use tokio::fs;

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};

use bittorrent_bencode::serde as serde_bencode;
use bittorrent_metainfo::Metainfo;
use bittorrent_storage::{file, single, Storage};

#[derive(Debug, Parser)]
struct Program {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    #[arg(long, value_enum)]
    mode: Mode,
    metainfo: PathBuf,
    torrent_dir: PathBuf,
}

#[derive(Clone, Debug, ValueEnum)]
enum Mode {
    File,
    Single,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        const BLOCK_SIZE: u64 = 16384;

        let metainfo_owner = fs::read(&self.metainfo).await?;
        let metainfo: Metainfo =
            serde_bencode::from_bytes(&metainfo_owner).map_err(Error::other)?;
        let dim = metainfo.info.new_dimension(BLOCK_SIZE);

        let mut storage: Box<dyn Storage> = match self.mode {
            Mode::File => {
                Box::new(file::Storage::open(&metainfo.info, dim, &self.torrent_dir).await?)
            }
            Mode::Single => {
                Box::new(single::Storage::open(&metainfo.info, dim, &self.torrent_dir).await?)
            }
        };

        let bitfield = storage.scan().await?;
        println!(
            "number of downloaded pieces: {} / {}",
            bitfield.count_ones(),
            bitfield.len()
        );

        Ok(())
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let prog = Program::parse();
    prog.tracing.init();
    prog.parameters.init();
    prog.execute().await
}
