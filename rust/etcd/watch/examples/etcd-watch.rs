use std::sync::Arc;

use clap::{Args, Parser};
use tokio::sync::broadcast::error::RecvError;

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};

use etcd_client::watch::Watch;
use etcd_client::{Client, Event};
use etcd_watch::{WatcherEvent, WatcherSpawner};

#[derive(Debug, Parser)]
#[command(after_help = ParametersConfig::render())]
struct Program {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    #[command(flatten)]
    watch_func: WatchFunc,

    #[arg(long)]
    start: Option<String>,
    #[arg(long)]
    end: Option<String>,
}

#[derive(Args, Debug)]
#[group(required = false, multiple = false)]
struct WatchFunc {
    #[arg(long)]
    prefix: bool,
    #[arg(long)]
    key: bool,
}

impl Program {
    async fn execute(self) {
        let spawner = WatcherSpawner::new();
        let mut event_recv = spawner.subscribe();
        let (_, mut guard) = spawner.spawn(Arc::new(Client::new()), self.watch());
        loop {
            match event_recv.recv().await {
                Ok(WatcherEvent::Init(kvs)) => {
                    println!("init");
                    for (key, value) in kvs {
                        println!(r#"  "{}": "{}""#, key.escape_ascii(), value.escape_ascii());
                    }
                }
                Ok(WatcherEvent::Event(Event::Create((key, value)))) => {
                    println!(
                        r#"create: "{}": "{}""#,
                        key.escape_ascii(),
                        value.escape_ascii(),
                    );
                }
                Ok(WatcherEvent::Event(Event::Update { key, new, old })) => {
                    println!(
                        r#"update: "{}": "{}" -> "{}""#,
                        key.escape_ascii(),
                        old.escape_ascii(),
                        new.escape_ascii(),
                    );
                }
                Ok(WatcherEvent::Event(Event::Delete((key, value)))) => {
                    println!(
                        r#"delete: "{}": "{}""#,
                        key.escape_ascii(),
                        value.escape_ascii(),
                    );
                }
                Err(RecvError::Closed) => break,
                Err(RecvError::Lagged(num_skipped)) => eprintln!("skip events: {num_skipped}"),
            }
        }
        guard.shutdown().await.unwrap().unwrap();
    }

    fn watch(&self) -> Watch {
        fn as_bytes(key: &Option<String>) -> Option<&[u8]> {
            key.as_ref().map(|key| key.as_ref())
        }

        if self.watch_func.prefix {
            Watch::prefix(self.start.clone().unwrap())
        } else if self.watch_func.key {
            Watch::key(self.start.clone().unwrap())
        } else {
            match (as_bytes(&self.start), as_bytes(&self.end)) {
                (Some(start), Some(end)) => Watch::range(start..end),
                (Some(start), None) => Watch::range(start..),
                (None, Some(end)) => Watch::range(..end),
                (None, None) => Watch::range::<&[u8]>(..),
            }
        }
    }
}

#[tokio::main]
async fn main() {
    let program = Program::parse();
    program.tracing.init();
    program.parameters.init();
    program.execute().await
}
