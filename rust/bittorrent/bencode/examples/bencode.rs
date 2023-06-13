use std::error;
use std::io::{self, Read, Write};

use bytes::BytesMut;
use clap::{Parser, ValueEnum};

use g1_serde::de::Either;

use bittorrent_bencode::serde as serde_bencode;

#[derive(Debug, Parser)]
struct Bencode {
    #[arg(long, value_enum, default_value_t = InputFormat::Bencode)]
    input: InputFormat,
    #[arg(long, value_enum, default_value_t = OutputFormat::Rust)]
    output: OutputFormat,
}

#[derive(Clone, Debug, ValueEnum)]
enum InputFormat {
    Bencode,
    Json,
}

#[derive(Clone, Debug, ValueEnum)]
enum OutputFormat {
    Bencode,
    Json,
    Rust,
}

fn main() -> Result<(), Box<dyn error::Error>> {
    let bencode = Bencode::parse();

    let mut input = Vec::new();
    io::stdin().read_to_end(&mut input)?;

    let mut deserializer = match bencode.input {
        InputFormat::Bencode => Either::Left(serde_bencode::Deserializer::from_bytes(&input)),
        InputFormat::Json => Either::Right(serde_json::Deserializer::from_slice(&input)),
    };

    match bencode.output {
        OutputFormat::Bencode => {
            let output = serde_transcode::transcode(&mut deserializer, serde_bencode::Serializer)?;
            let mut buffer = BytesMut::new();
            output.encode(&mut buffer);
            io::stdout().write_all(&buffer)?;
        }
        OutputFormat::Json => {
            let mut serializer = serde_json::Serializer::pretty(io::stdout());
            serde_transcode::transcode(&mut deserializer, &mut serializer)?;
            serializer.into_inner().flush()?;
        }
        OutputFormat::Rust => {
            let output = serde_transcode::transcode(&mut deserializer, serde_bencode::Serializer)?;
            println!("{:#?}", output);
        }
    }

    Ok(())
}
