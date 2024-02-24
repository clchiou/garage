use std::net::SocketAddr;

use snafu::prelude::*;

// These are `UtpSocket` errors, not connection errors.  (The latter are not exposed to the users
// for now, by the way.)
#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Error {
    #[snafu(display("udp socket was closed"))]
    Closed,
    #[snafu(display("duplicated utp connection: {peer_endpoint:?}"))]
    Duplicated { peer_endpoint: SocketAddr },
    #[snafu(display("utp handshake error: {peer_endpoint:?}"))]
    Handshake { peer_endpoint: SocketAddr },
    #[snafu(display("utp socket was shut down"))]
    Shutdown,
}
