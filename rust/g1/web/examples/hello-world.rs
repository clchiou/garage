use std::io::Error;
use std::net::SocketAddr;

use clap::Parser;
use tokio::net::{TcpListener, TcpSocket};

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_web::response;
use g1_web::service;
use g1_web::{Response, Server};

#[derive(Debug, Parser)]
#[command(after_help = ParametersConfig::render())]
struct Program {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    #[arg(long, default_value = "127.0.0.1:8000")]
    endpoint: SocketAddr,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        let (_, mut guard) = Server::spawn(
            self.bind()?,
            service::service_fn(|_| async {
                Response::new(response::body::full(b"Hello, World!"))
            }),
        );
        (&mut guard).await;
        guard.take_result()?
    }

    fn bind(&self) -> Result<TcpListener, Error> {
        let socket = TcpSocket::new_v4()?;
        socket.set_reuseaddr(true)?;
        socket.bind(self.endpoint)?;
        socket.listen(8)
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let program = Program::parse();
    program.tracing.init();
    program.parameters.init();
    program.execute().await
}
