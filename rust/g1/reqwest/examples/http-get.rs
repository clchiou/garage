use std::fs::OpenOptions;
use std::io::{self, Error, Write};
use std::path::PathBuf;

use clap::Parser;
use reqwest::Url;

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_reqwest::ClientBuilder;

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

        let mut response = client
            .get(self.url.clone())
            .send()
            .await
            .map_err(Error::other)?;

        eprintln!("{}", response.status());
        for (n, v) in response.headers() {
            eprintln!("{}: {}", n, v.as_bytes().escape_ascii());
        }

        let mut output = self.open()?;
        while let Some(chunk) = response.chunk().await.map_err(Error::other)? {
            output.write_all(&chunk)?;
        }

        Ok(())
    }

    fn open(&self) -> Result<Box<dyn Write>, Error> {
        Ok(match self.output.as_ref() {
            Some(output) => Box::new(
                OpenOptions::new()
                    .create(true)
                    .write(true)
                    .truncate(true)
                    .open(output)?,
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
