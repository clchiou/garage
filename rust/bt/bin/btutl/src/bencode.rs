use std::io::{self, Error, Read, Write};

use clap::{Args, Subcommand};
use serde_json::Deserializer;

use bt_bencode::{Json, Value, Yaml};

#[derive(Args, Debug)]
#[command(about = "Transcode Bencode data")]
pub(crate) struct BencodeCommand {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    #[command(about = "Transcode data from Bencode to JSON")]
    Json {
        #[arg(short, long, help = "Reverses the direction of transcoding")]
        reverse: bool,
    },
    #[command(about = "Transcode data from Bencode to YAML")]
    Yaml {
        #[arg(short, long, help = "Reverses the direction of transcoding")]
        reverse: bool,
    },
    #[command(about = "Print Bencode data")]
    Debug,
}

type Reader = Box<dyn FnMut() -> Result<Option<Value>, Error>>;
type Writer = Box<dyn FnMut(Value) -> Result<(), Error>>;

impl BencodeCommand {
    pub(crate) fn run(&self) -> Result<(), Error> {
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
    let mut stream = [serde_yaml::from_reader(reader).map_err(Error::other)].into_iter();
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
        writeln!(writer)
    })
}

fn yaml_writer<W>(mut writer: W) -> Writer
where
    W: Write + 'static,
{
    let mut first = true;
    Box::new(move |value| {
        if !first {
            writeln!(writer, "---")?;
        }
        first = false;
        serde_yaml::to_writer(&mut writer, &Yaml(&value)).map_err(Error::other)
    })
}

fn debug_writer<W>(mut writer: W) -> Writer
where
    W: Write + 'static,
{
    Box::new(move |value| writeln!(writer, "{value:#?}"))
}
