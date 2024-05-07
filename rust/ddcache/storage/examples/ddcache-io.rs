use std::fs::OpenOptions;
use std::io::Error;
use std::path::PathBuf;

use bytes::Bytes;
use chrono::Utc;
use clap::{Args, Parser, Subcommand};
use tokio::time::Instant;

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_tokio::os::Splice;

use ddcache_storage::{Storage, Timestamp};

#[derive(Debug, Parser)]
struct Program {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    #[arg(long, global = true, default_value = ".")]
    storage_dir: PathBuf,
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Size,
    Evict(Evict),
    Expire(Expire),
    Read(Read),
    Write(Write),
    Remove(Remove),
}

#[derive(Args, Debug)]
struct Evict {
    target_size: u64,
}

#[derive(Args, Debug)]
struct Expire {
    now: Option<Timestamp>,
}

#[derive(Args, Debug)]
struct Read {
    key: Bytes,
    file: PathBuf,
}

#[derive(Args, Debug)]
struct Write {
    key: Bytes,
    #[arg(long)]
    metadata: Option<Bytes>,
    file: PathBuf,
    #[arg(long)]
    expire_at: Option<Timestamp>,
}

#[derive(Args, Debug)]
struct Remove {
    key: Bytes,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        let storage = Storage::open(&self.storage_dir).await?;
        match &self.command {
            Command::Size => {
                eprintln!("size={}", storage.size());
            }
            Command::Evict(Evict { target_size }) => {
                let old_size = storage.size();
                let start = Instant::now();
                let new_size = storage.evict(*target_size).await?;
                let duration = start.elapsed();
                eprintln!(
                    "evict: old_size={} new_size={} duration={:?}",
                    old_size, new_size, duration,
                );
            }
            Command::Expire(Expire { now }) => {
                let old_size = storage.size();
                let start = Instant::now();
                storage.expire(now.unwrap_or(Utc::now())).await?;
                let duration = start.elapsed();
                let new_size = storage.size();
                eprintln!(
                    "expire : old_size={} new_size={} duration={:?}",
                    old_size, new_size, duration,
                );
            }
            Command::Read(Read { key, file }) => {
                let mut file = OpenOptions::new()
                    .create(true)
                    .write(true)
                    .truncate(true)
                    .open(file)?;
                let Some(reader) = storage.read(key.clone()).await else {
                    eprintln!("read: key not found: key={:?}", key);
                    return Ok(());
                };
                eprintln!("read: metadata={:?}", reader.metadata());
                eprintln!("read: expire_at={:?}", reader.expire_at());
                let size = usize::try_from(reader.size()).unwrap();
                reader.open()?.splice(&mut file, size).await?;
            }
            Command::Write(Write {
                key,
                metadata,
                file,
                expire_at,
            }) => {
                let mut file = OpenOptions::new().read(true).open(file)?;
                let size = usize::try_from(file.metadata()?.len()).unwrap();
                let mut writer = storage.write(key.clone(), /* truncate */ true).await?;
                writer.set_metadata(metadata.clone());
                writer.set_expire_at(*expire_at);
                file.splice(writer.open()?, size).await?;
                writer.commit()?;
            }
            Command::Remove(Remove { key }) => {
                eprintln!("remove: {:?}", storage.remove(key.clone()).await?);
            }
        }
        Ok(())
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let program = Program::parse();
    program.tracing.init();
    program.parameters.init();
    program.execute().await
}
