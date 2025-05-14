use std::io::Error;
use std::net::SocketAddr;
use std::sync::Arc;

use clap::Parser;
use futures::future::FutureExt;
use http_body_util::BodyExt;
use hyper::client::conn::http1;
use hyper::header::HOST;
use hyper::upgrade;
use hyper::{Method, StatusCode};
use hyper_util::rt::TokioIo;
use tokio::io;
use tokio::net::{TcpSocket, TcpStream};
use tokio::signal;
use tracing::Instrument;

use g1_cli::{param::ParametersConfig, tracing::TracingConfig};
use g1_tokio::net;
use g1_tokio::net::tcp::TcpListenerBuilder;
use g1_tokio::task::{JoinGuard, JoinQueue};
use g1_web::response;
use g1_web::service;
use g1_web::{Request, Response, Server};

g1_param::define!(incoming: Vec<TcpListenerBuilder> = vec![
    TcpListenerBuilder {
        endpoint: "127.0.0.1:8080".parse().expect("endpoint"),
        ..Default::default()
    },
]);

g1_param::define!(
    /// Connect to the upstream servers at the specified address.
    outgoing: Option<SocketAddr> = None;
);

/// Forward proxy based on HTTP CONNECT tunneling.
///
/// NOTE: This is a naive implementation and lacks security measures required for production use.
#[derive(Debug, Parser)]
#[command(version = g1_cli::version!(), after_help = ParametersConfig::render())]
struct Httpxd {
    #[command(flatten)]
    tracing: TracingConfig,
    #[command(flatten)]
    parameters: ParametersConfig,
}

impl Httpxd {
    async fn execute(&self) -> Result<(), Error> {
        let outgoing = *outgoing();
        if outgoing.is_some_and(|outgoing| outgoing.port() != 0) {
            tracing::warn!("outgoing port is not ephemeral");
        }

        let proxies = JoinQueue::new();
        let tunnels = Arc::new(JoinQueue::new());
        for incoming in incoming() {
            let (listener, _) = incoming.build()?;
            let tunnels = tunnels.clone();
            let (_, guard) = Server::spawn(
                listener,
                service::service_fn(move |request| proxy(request, outgoing, tunnels.clone())),
            );
            proxies.push(guard).expect("proxies");
        }

        tokio::select! {
            () = signal::ctrl_c().map(Result::unwrap) => tracing::info!("ctrl-c received!"),
            () = proxies.joinable() => tracing::warn!("proxy crash"),
            () = join_tunnels(&tunnels) => tracing::warn!("join_tunnels return"),
        }

        tokio::try_join!(
            proxies.shutdown().map(|r| r?),
            tunnels.shutdown().map(|r| r?),
        )?;
        Ok(())
    }
}

async fn proxy(
    request: Request,
    outgoing: Option<SocketAddr>,
    tunnels: Arc<JoinQueue<Result<(), Error>>>,
) -> Response {
    if request.method() != Method::CONNECT {
        // This is non-standard.  We will make our best effort to proxy the client's request.
        return proxy_non_standard(request, outgoing, tunnels).await;
    }

    let Some((host, port)) = request
        .uri()
        .authority()
        .map(|authority| (authority.host(), authority.port_u16().unwrap_or(80)))
    else {
        tracing::debug!("request target is missing");
        return new_response(StatusCode::BAD_REQUEST);
    };

    let server = match connect(host, port, outgoing).await {
        Ok(server) => server,
        Err(response) => return response,
    };

    // According to [doc], the response must be sent before waiting for the connection upgrade.
    // [doc]: https://docs.rs/hyper/latest/hyper/upgrade/index.html#server
    if tunnels
        .push(JoinGuard::spawn(move |cancel| {
            async move {
                tokio::select! {
                    () = cancel.wait() => Ok(()),
                    result = tunnel(request, server) => result,
                }
            }
            .instrument(tracing::info_span!("httpxd", ?outgoing))
        }))
        .is_err()
    {
        tracing::debug!("tunnels closed");
        return new_response(StatusCode::SERVICE_UNAVAILABLE);
    }

    new_response(StatusCode::OK)
}

async fn proxy_non_standard(
    request: Request,
    outgoing: Option<SocketAddr>,
    tunnels: Arc<JoinQueue<Result<(), Error>>>,
) -> Response {
    let Some((host, port)) = request.headers().get(HOST).and_then(|host| {
        let host = host.to_str().ok()?;
        Some(match host.split_once(':') {
            Some((host, port)) => (host, port.parse().ok()?),
            None => (host, 80),
        })
    }) else {
        tracing::debug!("host header is missing or invalid");
        return new_response(StatusCode::BAD_REQUEST);
    };

    let server = match connect(host, port, outgoing).await {
        Ok(server) => server,
        Err(response) => return response,
    };

    let (mut sender, conn) = match http1::Builder::new().handshake(TokioIo::new(server)).await {
        Ok(pair) => pair,
        Err(error) => {
            tracing::warn!(%error, "handshake");
            return new_response(StatusCode::BAD_GATEWAY);
        }
    };

    // The [doc] states that `conn` must be `await`-ed for `sender` to make progress.  However, for
    // reasons that are unclear to me, using `tokio::try_join!` does not work, and instead, we have
    // to spawn a proper new task.
    //
    // [doc]: https://docs.rs/hyper/latest/hyper/client/conn/http1/struct.Builder.html#method.handshake
    if tunnels
        .push(JoinGuard::spawn(move |cancel| async move {
            if let Err(error) = tokio::select! {
                () = cancel.wait() => Ok(()),
                result = conn => result,
            } {
                tracing::warn!(%error, "connection");
            }
            Ok(())
        }))
        .is_err()
    {
        tracing::debug!("tunnels closed");
        return new_response(StatusCode::SERVICE_UNAVAILABLE);
    }

    match sender.send_request(request).await {
        Ok(response) => response.map(|body| body.map_err(Error::other).boxed()),
        Err(error) => {
            tracing::warn!(%error, "request");
            new_response(StatusCode::BAD_GATEWAY)
        }
    }
}

async fn tunnel(request: Request, mut server: TcpStream) -> Result<(), Error> {
    let mut client = TokioIo::new(upgrade::on(request).await.map_err(Error::other)?);
    let (num_bytes_send, num_bytes_recv) = io::copy_bidirectional(&mut client, &mut server).await?;
    tracing::debug!(num_bytes_send, num_bytes_recv, "tunnel");
    Ok(())
}

async fn join_tunnels(tunnels: &JoinQueue<Result<(), Error>>) {
    while let Some(mut guard) = tunnels.join_next().await {
        match guard.take_result() {
            Ok(Ok(())) => {}
            Ok(Err(error)) => tracing::warn!(%error, "tunnel"),
            Err(error) => tracing::warn!(%error, "tunnel task"),
        }
    }
}

async fn connect(
    host: &str,
    port: u16,
    outgoing: Option<SocketAddr>,
) -> Result<TcpStream, Response> {
    tracing::debug!(%host, %port, "connect");

    // TODO: Should we cache DNS lookup results?
    let server = match net::lookup_host_first((host, port)).await {
        Ok(server) => server,
        Err(error) => {
            tracing::warn!(%host, %port, %error, "lookup_host_first");
            return Err(new_response(StatusCode::INTERNAL_SERVER_ERROR));
        }
    };

    async {
        let socket = if server.is_ipv4() {
            TcpSocket::new_v4()
        } else {
            assert!(server.is_ipv6());
            TcpSocket::new_v6()
        }?;
        if let Some(outgoing) = outgoing {
            socket.bind(outgoing)?;
        }
        socket.connect(server).await
    }
    .await
    .map_err(|error| {
        tracing::warn!(%error, "connect");
        new_response(StatusCode::BAD_GATEWAY)
    })
}

fn new_response(status: StatusCode) -> Response {
    response::Builder::new()
        .status(status)
        .body(response::body::empty())
        .expect("response")
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let httpxd = Httpxd::parse();
    httpxd.tracing.init();
    httpxd.parameters.init();
    httpxd.execute().await
}
