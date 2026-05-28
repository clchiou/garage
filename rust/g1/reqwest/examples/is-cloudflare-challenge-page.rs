use clap::Parser;
use reqwest::{Error, Url};

use g1_reqwest::ResponseExt;

#[derive(Debug, Parser)]
struct Program {
    url: Url,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        let response = reqwest::get(self.url.clone()).await?;
        eprintln!("{}", response.is_cloudflare_challenge_page());
        Ok(())
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    Program::parse().execute().await
}
