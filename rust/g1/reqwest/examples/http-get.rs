use std::io::Error;
use std::path::PathBuf;

use clap::Parser;
use reqwest::Url;
use tokio::fs::OpenOptions;
use tokio::io::{self, AsyncWrite};

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_reqwest::{ClientBuilder, ResponseExt};

g1_param::define!(client: ClientBuilder = Default::default());

#[derive(Debug, Parser)]
#[command(after_help = ParametersConfig::render())]
struct Program {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    url: Url,
    output: Option<PathBuf>,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        let client = client().clone().build().map_err(Error::other)?;

        let response = client
            .get(self.url.clone())
            .send()
            .await
            .map_err(Error::other)?;

        eprintln!("{}", response.status());
        for (n, v) in response.headers() {
            eprintln!("{}: {}", n, v.as_bytes().escape_ascii());
        }

        io::copy(&mut response.reader(), &mut self.open().await?).await?;

        Ok(())
    }

    async fn open(&self) -> Result<Box<dyn AsyncWrite + Unpin>, Error> {
        Ok(match self.output.as_ref() {
            Some(output) => Box::new(
                OpenOptions::new()
                    .create(true)
                    .write(true)
                    .truncate(true)
                    .open(output)
                    .await?,
            ),
            None => Box::new(io::stdout()),
        })
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let program = Program::parse();
    program.tracing.init();
    program.parameters.init();
    program.execute().await
}
