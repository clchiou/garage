use std::fs;
use std::io::Error;
use std::path::PathBuf;
use std::str::FromStr;

use bytes::Bytes;
use clap::{Args, Parser};

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};

use bittorrent_actor::{Actors, Mode, StorageOpen};
use bittorrent_base::{InfoHash, MagnetUri};
use bittorrent_metainfo::{InfoOwner, MetainfoOwner};

#[derive(Debug, Parser)]
struct Program {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    #[command(flatten)]
    torrent_source: TorrentSource,
    #[command(flatten)]
    output: Output,
}

#[derive(Args, Debug)]
#[group(required = true, multiple = false)]
struct TorrentSource {
    #[arg(long)]
    metainfo: Option<PathBuf>,
    #[arg(long, value_parser = MagnetUri::from_str)]
    magnet_uri: Option<MagnetUri>,
    #[arg(long)]
    info: Option<PathBuf>,
    #[arg(long, value_parser = InfoHash::from_str)]
    info_hash: Option<InfoHash>,
}

#[derive(Args, Debug)]
#[group(required = true, multiple = false)]
struct Output {
    #[arg(long)]
    file: Option<PathBuf>,
    #[arg(long)]
    single: Option<PathBuf>,
}

impl Program {
    async fn execute(self) -> Result<(), Error> {
        let (mode, info_hash) = self.torrent_source.into_mode()?;
        let mut actors = Actors::spawn(mode, info_hash, self.output.into_open()).await?;
        actors.join_any().await;
        actors.shutdown_all().await
    }
}

impl TorrentSource {
    fn into_mode(self) -> Result<(Mode, InfoHash), Error> {
        if let Some(metainfo_path) = self.metainfo {
            let metainfo = MetainfoOwner::try_from(Bytes::from(fs::read(&metainfo_path)?))
                .map_err(Error::other)?;
            let info_hash = InfoHash::new(metainfo.deref().info.compute_info_hash());
            Ok((Mode::Tracker(metainfo), info_hash))
        } else if let Some(mut magnet_uri) = self.magnet_uri {
            // TODO: Support multiple downloads.
            Ok((
                Mode::Trackerless(None),
                magnet_uri.info_hashes.pop().unwrap(),
            ))
        } else if let Some(info_path) = self.info {
            let info =
                InfoOwner::try_from(Bytes::from(fs::read(&info_path)?)).map_err(Error::other)?;
            let info_hash = InfoHash::new(info.deref().compute_info_hash());
            Ok((Mode::Trackerless(Some(info)), info_hash))
        } else {
            Ok((Mode::Trackerless(None), self.info_hash.unwrap()))
        }
    }
}

impl Output {
    fn into_open(self) -> StorageOpen {
        if let Some(output_dir) = self.file {
            StorageOpen::File(output_dir)
        } else {
            StorageOpen::Single(self.single.unwrap())
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let program = Program::parse();
    program.tracing.init();
    program.parameters.init();
    program.execute().await
}
