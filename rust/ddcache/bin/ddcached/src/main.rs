use std::io::Error;
use std::path::PathBuf;

use clap::Parser;
use futures::future::FutureExt;
use tokio::signal;

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};

use ddcache_server::Server;

#[derive(Debug, Parser)]
struct Ddcached {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    storage_dir: PathBuf,
}

impl Ddcached {
    async fn execute(&self) -> Result<(), Error> {
        let (_, mut guard) = Server::spawn(&self.storage_dir).await?;
        tokio::select! {
            () = signal::ctrl_c().map(Result::unwrap) => tracing::info!("ctrl-c received!"),
            () = guard.joinable() => {}
        }
        guard.shutdown().await?
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let ddcached = Ddcached::parse();
    ddcached.tracing.init();
    ddcached.parameters.init();
    ddcached.execute().await
}
