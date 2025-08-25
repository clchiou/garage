use std::io::{self, Error};

use clap::{Args, ValueEnum};
use url::Url;

use bt_base::{InfoHash, PeerId};
use bt_tracker::{Client, Request};

use crate::text::Format;

#[derive(Args, Debug)]
#[command(about = "Send an announcement to a tracker")]
pub(crate) struct TrackerCommand {
    #[arg(value_name = "URL", help = "Tracker announce URL")]
    endpoint: Url,

    info_hash: InfoHash,

    #[arg(long, value_name = "ID", help = "Peer id")]
    self_id: Option<PeerId>,

    #[arg(long, help = "Peer address")]
    ip: Option<String>,
    #[arg(long, default_value_t = 6881, help = "Peer port")]
    port: u16,

    #[arg(
        long,
        value_name = "N",
        default_value_t = 0,
        help = "Total amount uploaded"
    )]
    uploaded: u64,
    #[arg(
        long,
        value_name = "N",
        default_value_t = 0,
        help = "Total amount downloaded"
    )]
    downloaded: u64,
    #[arg(
        long,
        value_name = "N",
        default_value_t = 0,
        help = "Number of bytes left"
    )]
    left: u64,

    #[arg(long, value_enum, help = "Peer event")]
    event: Option<Event>,

    #[arg(long, value_name = "N", help = "Want this many peers in response")]
    num_want: Option<usize>,

    #[arg(long, value_name = "KEY", help = "Secret peer key")]
    key: Option<String>,

    #[arg(long, value_name = "ID", help = "Tracker id")]
    tracker_id: Option<String>,

    #[arg(long, value_name = "BOOL", help = "Send compact peers in response")]
    compact: Option<bool>,

    #[arg(long, value_name = "BOOL", help = "Send peer ids in response")]
    no_peer_id: Option<bool>,

    #[arg(long, value_enum, default_value_t = Format::Debug, help = "Output format")]
    format: Format,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, ValueEnum)]
enum Event {
    Started,
    Completed,
    Stopped,
}

impl TrackerCommand {
    pub(crate) async fn run(&self) -> Result<(), Error> {
        let response = Client::new()
            .announce(self.endpoint.clone(), &self.make_request())
            .await
            .map_err(Error::other)?;
        let output = io::stdout();
        self.format.write(&response, output)
    }

    fn make_request(&self) -> Request {
        Request {
            info_hash: self.info_hash.clone(),
            self_id: self.self_id.clone().unwrap_or_else(rand::random),
            ip: self.ip.clone(),
            port: self.port,
            uploaded: self.uploaded,
            downloaded: self.downloaded,
            left: self.left,
            event: self.event.map(bt_tracker::Event::from),
            num_want: self.num_want,
            key: self.key.clone(),
            tracker_id: self.tracker_id.clone(),
            compact: self.compact,
            no_peer_id: self.no_peer_id,
        }
    }
}

impl From<Event> for bt_tracker::Event {
    fn from(event: Event) -> Self {
        match event {
            Event::Started => Self::Started,
            Event::Completed => Self::Completed,
            Event::Stopped => Self::Stopped,
        }
    }
}
