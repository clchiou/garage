use std::error;
use std::io::{self, Read, Write};

use clap::{Parser, Subcommand};
use serde_json::Deserializer;

use bt_bencode::{Json, Value, Yaml};

#[derive(Debug, Parser)]
struct Bencode {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Json {
        #[arg(short, long)]
        reverse: bool,
    },
    Yaml {
        #[arg(short, long)]
        reverse: bool,
    },
    Debug,
}

type Reader = Box<dyn FnMut() -> Result<Option<Value>, Error>>;
type Writer = Box<dyn FnMut(Value) -> Result<(), Error>>;

type Error = Box<dyn error::Error>;

impl Bencode {
    fn execute(&self) -> Result<(), Error> {
        let reader = io::stdin();
        let reader = match self.command {
            Command::Json { reverse: true } => json_reader(reader),
            Command::Yaml { reverse: true } => yaml_reader(reader),
            _ => bencode_reader(reader),
        };

        let writer = io::stdout();
        let writer = match self.command {
            Command::Json { reverse: false } => json_writer(writer),
            Command::Yaml { reverse: false } => yaml_writer(writer),
            Command::Debug => debug_writer(writer),
            _ => bencode_writer(writer),
        };

        transcode(reader, writer)
    }
}

fn transcode(mut reader: Reader, mut writer: Writer) -> Result<(), Error> {
    while let Some(value) = reader()? {
        writer(value)?;
    }
    Ok(())
}

fn bencode_reader<R>(mut reader: R) -> Reader
where
    R: Read + 'static,
{
    Box::new(move || Ok(bt_bencode::from_reader(&mut reader)?))
}

fn json_reader<R>(reader: R) -> Reader
where
    R: Read + 'static,
{
    let mut stream = Deserializer::from_reader(reader).into_iter();
    Box::new(move || Ok(stream.next().transpose()?))
}

fn yaml_reader<R>(reader: R) -> Reader
where
    R: Read,
{
    // `serde_yaml` does not support the deserialization of multiple documents.
    let mut stream = [serde_yaml::from_reader(reader)].into_iter();
    Box::new(move || Ok(stream.next().transpose()?.map(|Yaml(value)| value)))
}

fn bencode_writer<W>(mut writer: W) -> Writer
where
    W: Write + 'static,
{
    Box::new(move |value| Ok(bt_bencode::to_writer(&mut writer, &value)?))
}

fn json_writer<W>(mut writer: W) -> Writer
where
    W: Write + 'static,
{
    Box::new(move |value| {
        serde_json::to_writer(&mut writer, &Json(&value))?;
        std::writeln!(writer)?;
        Ok(())
    })
}

fn yaml_writer<W>(mut writer: W) -> Writer
where
    W: Write + 'static,
{
    let mut first = true;
    Box::new(move |value| {
        if !first {
            std::writeln!(writer, "---")?;
        }
        first = false;
        Ok(serde_yaml::to_writer(&mut writer, &Yaml(&value))?)
    })
}

fn debug_writer<W>(mut writer: W) -> Writer
where
    W: Write + 'static,
{
    Box::new(move |value| Ok(std::writeln!(writer, "{value:#?}")?))
}

fn main() -> Result<(), Error> {
    Bencode::parse().execute()
}
