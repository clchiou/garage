use std::fs::File;
use std::io::{Error, ErrorKind};
use std::net::SocketAddr;
use std::path::PathBuf;

use clap::Parser;
use hyper::StatusCode;
use tokio::net::{TcpListener, TcpSocket};

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_web::response;
use g1_web::{Handler, Request, Response, Server};

#[derive(Debug, Parser)]
#[command(after_help = ParametersConfig::render())]
struct Program {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,

    #[arg(long, default_value = "127.0.0.1:8000")]
    endpoint: SocketAddr,
    #[arg(default_value = ".")]
    dir: PathBuf,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        let dir = self.dir.clone();
        let (_, mut guard) = Server::spawn(
            self.bind()?,
            (move |request| handle(dir.clone(), request)).into_service(),
        );
        guard.join().await;
        guard.take_result()?
    }

    fn bind(&self) -> Result<TcpListener, Error> {
        let socket = TcpSocket::new_v4()?;
        socket.set_reuseaddr(true)?;
        socket.bind(self.endpoint)?;
        socket.listen(8)
    }
}

// NOTE: This is **not** safe because clients can traverse to parent directories.
async fn handle(mut path: PathBuf, request: Request) -> Result<Response, HandlerError> {
    path.push(
        request
            .uri()
            .path()
            .strip_prefix('/')
            .ok_or(HandlerError::InvalidPath)?,
    );
    tracing::info!(?path, "get");
    if !path.is_file() {
        return Err(HandlerError::InvalidPath);
    }
    Ok(Response::new(response::body::file(File::open(path)?)?))
}

#[derive(Clone, Copy)]
enum HandlerError {
    InvalidPath,
    NotFound,
    Other,
}

impl From<Error> for HandlerError {
    fn from(error: Error) -> Self {
        tracing::warn!(%error, "handler");
        match error.kind() {
            ErrorKind::NotFound => HandlerError::NotFound,
            _ => HandlerError::Other,
        }
    }
}

impl From<HandlerError> for Response {
    fn from(error: HandlerError) -> Self {
        response::Builder::new()
            .status(match error {
                HandlerError::InvalidPath => StatusCode::BAD_REQUEST,
                HandlerError::NotFound => StatusCode::NOT_FOUND,
                HandlerError::Other => StatusCode::INTERNAL_SERVER_ERROR,
            })
            .body(response::body::empty())
            .expect("response")
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let program = Program::parse();
    program.tracing.init();
    program.parameters.init();
    program.execute().await
}
