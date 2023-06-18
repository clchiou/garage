use std::error;
use std::io::{self, Read, Write};

use clap::{Parser, ValueEnum};

use g1_base::fmt::Hex;

use bittorrent_bencode::serde as serde_bencode;
use bittorrent_metainfo::Metainfo;

#[derive(Debug, Parser)]
struct Cli {
    #[arg(long, value_enum, default_value_t = Output::Rust)]
    output: Output,
}

#[derive(Clone, Debug, ValueEnum)]
enum Output {
    Bencode,
    InfoHash,
    Rust,
}

fn main() -> Result<(), Box<dyn error::Error>> {
    let cli = Cli::parse();
    let mut input = Vec::new();
    io::stdin().read_to_end(&mut input)?;
    let metainfo: Metainfo = serde_bencode::from_bytes(&input)?;
    match cli.output {
        Output::Bencode => {
            io::stdout().write_all(&serde_bencode::to_bytes(&metainfo)?)?;
        }
        Output::InfoHash => {
            println!("{:?}", Hex(&metainfo.info.compute_info_hash()));
        }
        Output::Rust => {
            println!("{:#?}", metainfo);
        }
    }
    Ok(())
}
