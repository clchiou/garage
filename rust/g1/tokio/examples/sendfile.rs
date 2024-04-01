// Verify that `SendFile` and `Splice` accept non-tokio I/O types.
use std::fs::File;
use std::io::Error;
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::time::{Duration, Instant};

use clap::Parser;
use tokio::task;
use tokio::time;

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_tokio::os::{SendFile, Splice};

#[derive(Debug, Parser)]
struct Program {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    #[arg(long)]
    recv: bool,
    #[arg(long, default_value = "127.0.0.1:8000")]
    endpoint: SocketAddr,

    file: PathBuf,
    #[arg(long)]
    offset: Option<i64>,
    #[arg(long, default_value_t = 4096)]
    count: usize,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        tokio::select! {
            result = async {
                if self.recv {
                    self.splice().await
                } else {
                    self.sendfile().await
                }
            } => {
                let (size, elapsed) = result?;
                eprintln!(
                    "size={} elapsed={:?} rate={} B/s",
                    size,
                    elapsed,
                    f64::from(u32::try_from(size).unwrap()) / elapsed.as_secs_f64(),
                );
            }
            // Verify that and `sendfile` and `splice` do not accidentally block the main loop.
            () = async {
                let mut interval = time::interval(Duration::from_millis(100));
                loop {
                    interval.tick().await;
                    eprintln!("tick!");
                }
            } => {}
        }
        Ok(())
    }

    async fn sendfile(&self) -> Result<(usize, Duration), Error> {
        let endpoint = self.endpoint;
        let mut stream = task::spawn_blocking(move || TcpStream::connect(endpoint))
            .await
            .unwrap()?;
        let mut file = File::open(&self.file)?;
        eprintln!("sendfile");
        let start = Instant::now();
        stream
            .sendfile(&mut file, self.offset, self.count)
            .await
            .map(|size| (size, start.elapsed()))
    }

    async fn splice(&self) -> Result<(usize, Duration), Error> {
        let endpoint = self.endpoint;
        let mut stream =
            task::spawn_blocking(move || TcpListener::bind(endpoint)?.incoming().next().unwrap())
                .await
                .unwrap()?;
        let mut file = File::create(&self.file)?;
        eprintln!("splice");
        let start = Instant::now();
        stream
            .splice(&mut file, self.count)
            .await
            .map(|size| (size, start.elapsed()))
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let program = Program::parse();
    program.tracing.init();
    program.parameters.init();
    program.execute().await
}
