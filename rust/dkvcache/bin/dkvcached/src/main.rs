use std::io::Error;
use std::path::PathBuf;

use clap::Parser;
use futures::future::FutureExt;
use tokio::signal;

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};

use dkvcache_server::Server;

#[derive(Debug, Parser)]
#[command(version = g1_cli::version!(), after_help = ParametersConfig::render())]
struct Dkvcached {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    storage_path: PathBuf,
}

impl Dkvcached {
    async fn execute(&self) -> Result<(), Error> {
        let (_, mut guard) = Server::spawn(&self.storage_path).await?;
        tokio::select! {
            () = signal::ctrl_c().map(Result::unwrap) => tracing::info!("ctrl-c received!"),
            () = guard.joinable() => {}
        }
        guard.shutdown().await?
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let dkvcached = Dkvcached::parse();
    dkvcached.tracing.init();
    dkvcached.parameters.init();
    dkvcached.execute().await
}
