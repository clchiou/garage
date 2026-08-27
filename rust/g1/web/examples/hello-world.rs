use std::io::Error;
use std::net::SocketAddr;
use std::time::Duration;

use bytes::Bytes;
use clap::Parser;
use futures::stream::{self, StreamExt};
use tokio::net::{TcpListener, TcpSocket};
use tokio::time;

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
            service::service_fn(|request| async move {
                if request.uri().path() == "/stream" {
                    Response::new(response::body::stream(
                        stream::iter(b"Hello, World!".windows(1)).then(|bytes| async move {
                            time::sleep(Duration::from_secs(1)).await;
                            Ok(Bytes::from_static(bytes))
                        }),
                    ))
                } else {
                    Response::new(response::body::full(b"Hello, World!"))
                }
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
