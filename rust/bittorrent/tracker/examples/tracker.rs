use std::error::Error;
use std::path::PathBuf;

use clap::{Parser, ValueEnum};
use futures::future::FutureExt;
use tokio::fs;
use tokio::signal;

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};

use bittorrent_base::InfoHash;
use bittorrent_bencode::serde as serde_bencode;
use bittorrent_metainfo::Metainfo;
use bittorrent_tracker::{
    client::Client,
    request::{Event, Request},
    Tracker,
};

#[derive(Debug, Parser)]
struct Program {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    #[arg(long)]
    tracker: bool,

    #[arg(long, default_value_t = 6881)]
    port: u16,
    #[arg(long, default_value_t = 0)]
    num_bytes_send: u64,
    #[arg(long, default_value_t = 0)]
    num_bytes_recv: u64,
    #[arg(long, default_value_t = 0)]
    num_bytes_left: u64,
    #[arg(long)]
    event: Option<EventEnum>,

    metainfo: PathBuf,
}

#[derive(Clone, Debug, ValueEnum)]
enum EventEnum {
    Started,
    Completed,
    Stopped,
}

#[derive(Debug)]
struct Torrent {
    num_bytes_send: u64,
    num_bytes_recv: u64,
    num_bytes_left: u64,
}

impl Program {
    async fn execute(&self) -> Result<(), Box<dyn Error>> {
        let self_id = bittorrent_base::self_id().clone();
        tracing::info!(?self_id);

        let metainfo_owner = fs::read(&self.metainfo).await?;
        let metainfo: Metainfo = serde_bencode::from_bytes(&metainfo_owner)?;

        if self.tracker {
            let (tracker, mut tracker_guard) = Tracker::spawn(
                &metainfo,
                InfoHash::new(metainfo.info.compute_info_hash()),
                self.port,
                Torrent::new(
                    self.num_bytes_send,
                    self.num_bytes_recv,
                    self.num_bytes_left,
                ),
            );
            tokio::select! {
                () = signal::ctrl_c().map(Result::unwrap) => eprintln!("ctrl-c received!"),
                () = async {
                    tracker.start();
                    while let Some(peer) = tracker.next().await {
                        println!("{:?}", peer);
                    }
                } => {}
            }
            // I do not fully understand why, but Rust does not automatically implement
            // `From<Box<dyn Error + Send>>` for `Box<dyn Error>`, and thus `?` does not work.
            if let Err(error) = tracker_guard.shutdown().await? {
                return Err(error);
            }
        } else {
            let mut client = Client::new(&metainfo);
            let request = Request::new(
                InfoHash::new(metainfo.info.compute_info_hash()),
                self_id,
                self.port,
                self.num_bytes_send,
                self.num_bytes_recv,
                self.num_bytes_left,
                self.event.clone().map(Event::from),
            );
            let response = client.get(&request).await?;
            println!("{:#?}", response.deref());
        }

        Ok(())
    }
}

impl From<EventEnum> for Event {
    fn from(event: EventEnum) -> Self {
        match event {
            EventEnum::Started => Self::Started,
            EventEnum::Completed => Self::Completed,
            EventEnum::Stopped => Self::Stopped,
        }
    }
}

impl Torrent {
    fn new(num_bytes_send: u64, num_bytes_recv: u64, num_bytes_left: u64) -> Self {
        Self {
            num_bytes_send,
            num_bytes_recv,
            num_bytes_left,
        }
    }
}

impl bittorrent_tracker::Torrent for Torrent {
    fn num_bytes_send(&self) -> u64 {
        self.num_bytes_send
    }

    fn num_bytes_recv(&self) -> u64 {
        self.num_bytes_recv
    }

    fn num_bytes_left(&self) -> u64 {
        self.num_bytes_left
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let program = Program::parse();
    program.tracing.init();
    program.parameters.init();
    program.execute().await
}
