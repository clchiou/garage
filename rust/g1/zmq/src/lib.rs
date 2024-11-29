#[cfg(feature = "client")]
pub mod client;
pub mod duplex;
pub mod envelope;

use std::io::Error;
use std::os::fd::{AsRawFd, RawFd};
use std::string::FromUtf8Error;

use tokio::io::unix::AsyncFd;
use zmq::{Mechanism, Message, PollEvents, SocketType, DONTWAIT};

use g1_base::fmt::{DebugExt, InsertPlaceholder};

#[cfg(feature = "param")]
mod param {
    use std::marker::PhantomData;

    use serde::Deserialize;

    pub trait SocketTypeParam {
        const SOCKET_TYPE: zmq::SocketType;
    }

    macro_rules! socket_type_param {
        ($name:ident, $variant:ident $(,)?) => {
            #[derive(Clone, Debug)]
            pub struct $name;

            impl SocketTypeParam for $name {
                const SOCKET_TYPE: zmq::SocketType = zmq::SocketType::$variant;
            }
        };
    }

    socket_type_param!(Pair, PAIR);
    socket_type_param!(Pub, PUB);
    socket_type_param!(Sub, SUB);
    socket_type_param!(Req, REQ);
    socket_type_param!(Rep, REP);
    socket_type_param!(Dealer, DEALER);
    socket_type_param!(Router, ROUTER);
    socket_type_param!(Pull, PULL);
    socket_type_param!(Push, PUSH);
    socket_type_param!(Xpub, XPUB);
    socket_type_param!(Xsub, XSUB);
    socket_type_param!(Stream, STREAM);

    #[derive(Clone, Debug, Deserialize)]
    #[serde(default, deny_unknown_fields)]
    pub struct SocketBuilder<T> {
        pub linger: Option<i32>,

        pub bind: Vec<String>,
        pub connect: Vec<String>,

        // Declare `pub` so that `SocketBuilder` can be initialized using `..Default::default()`.
        pub _socket_type: PhantomData<T>,
    }

    impl<T> Default for SocketBuilder<T> {
        fn default() -> Self {
            Self {
                linger: Some(0), // Do NOT block the program exit!

                bind: Vec::new(),
                connect: Vec::new(),

                _socket_type: PhantomData,
            }
        }
    }

    impl<T> SocketBuilder<T> {
        pub fn linger(&mut self, linger: Option<i32>) -> &mut Self {
            self.linger = linger;
            self
        }

        pub fn bind(&mut self, endpoint: String) -> &mut Self {
            self.bind.push(endpoint);
            self
        }

        pub fn connect(&mut self, endpoint: String) -> &mut Self {
            self.connect.push(endpoint);
            self
        }
    }

    impl<T: SocketTypeParam> SocketBuilder<T> {
        pub fn build(
            &self,
            context: &zmq::Context,
        ) -> Result<(zmq::Socket, Vec<String>), zmq::Error> {
            let socket = context.socket(T::SOCKET_TYPE)?;

            if let Some(linger) = self.linger {
                socket.set_linger(linger)?;
            }

            let mut bind_endpoints = Vec::with_capacity(self.bind.len());
            for endpoint in &self.bind {
                socket.bind(endpoint)?;
                bind_endpoints.push(socket.get_last_endpoint()?.expect("endpoint"));
            }

            for endpoint in &self.connect {
                socket.connect(endpoint)?;
            }

            Ok((socket, bind_endpoints))
        }
    }
}

#[cfg(feature = "param")]
pub use self::param::{
    Dealer, Pair, Pub, Pull, Push, Rep, Req, Router, SocketBuilder, SocketTypeParam, Stream, Sub,
    Xpub, Xsub,
};

#[derive(DebugExt)]
pub struct Socket {
    #[debug(with = InsertPlaceholder)]
    socket: zmq::Socket,
    #[debug(with = InsertPlaceholder)]
    fd: AsyncFd<RawFd>,
}

// While `zmq::Socket` is not `Sync`, it seems correct to assert that our `Socket` is indeed
// `Sync`, considering that our `Socket` owns `zmq::Socket` and only exposes `&mut Self`.
//
// TODO: Can we prove this?
unsafe impl Sync for Socket {}

pub type Multipart = Vec<Message>;

impl TryFrom<zmq::Socket> for Socket {
    type Error = Error;

    fn try_from(socket: zmq::Socket) -> Result<Self, Self::Error> {
        Self::new(socket)
    }
}

// Be cautious of [`ZMQ_FD`](https://libzmq.readthedocs.io/en/latest/zmq_getsockopt.html)
// idiosyncrasies:
// * It is edge-triggered.
// * It only generates read notifications for `recv` and `send`.
macro_rules! io {
    ($self:ident . $method:ident ( $arg:expr, $flags:ident $(,)? )) => {
        loop {
            match $self.socket.$method($arg, $flags | DONTWAIT) {
                Err(zmq::Error::EAGAIN) if ($flags & DONTWAIT) == 0 => {
                    $self.fd.readable().await?.clear_ready();
                }
                result => return result.map_err(Error::from),
            }
        }
    };
}

impl Socket {
    pub fn new(socket: zmq::Socket) -> Result<Self, Error> {
        let fd = AsyncFd::new(socket.as_raw_fd())?;
        Ok(Self { socket, fd })
    }

    /// Returns a shared reference to the inner `zmq::Socket`.
    ///
    /// # Safety
    ///
    /// Most of the basic ZeroMQ [socket types], such as `ZMQ_REQ`, are not thread-safe.
    ///
    /// [socket types]: https://libzmq.readthedocs.io/en/latest/zmq_socket.html
    pub unsafe fn get_ref(&self) -> &zmq::Socket {
        &self.socket
    }

    pub fn get_mut(&mut self) -> &mut zmq::Socket {
        &mut self.socket
    }

    pub fn into_inner(self) -> zmq::Socket {
        self.socket
    }

    pub async fn recv(&mut self, message: &mut Message, flags: i32) -> Result<(), Error> {
        io!(self.recv(message, flags))
    }

    pub async fn recv_into(&mut self, bytes: &mut [u8], flags: i32) -> Result<usize, Error> {
        io!(self.recv_into(bytes, flags))
    }

    pub async fn recv_msg(&mut self, flags: i32) -> Result<Message, Error> {
        let mut message = Message::new();
        self.recv(&mut message, flags).await.map(|()| message)
    }

    pub async fn recv_bytes(&mut self, flags: i32) -> Result<Vec<u8>, Error> {
        self.recv_msg(flags).await.map(|message| message.to_vec())
    }

    pub async fn recv_string(&mut self, flags: i32) -> Result<Result<String, Vec<u8>>, Error> {
        self.recv_bytes(flags)
            .await
            .map(|bytes| String::from_utf8(bytes).map_err(FromUtf8Error::into_bytes))
    }

    pub async fn send<T>(&mut self, data: T, flags: i32) -> Result<(), Error>
    where
        T: Into<Message>,
    {
        let mut message = data.into();
        io!(self.send(&mut message, flags))
    }
}

macro_rules! forward {
    ($($name:ident($($arg:ident: $arg_type:ty),* $(,)?) -> $ret_type:ty);* $(;)?) => {
        $(
            pub fn $name(&mut self, $($arg : $arg_type),*) -> $ret_type {
                self.socket.$name($($arg),*)
            }
        )*
    };
}

macro_rules! sockopt {
    ($($getter:tt $setter:tt $type:ty);* $(;)?) => {
        $(
            sockopt!(@GETTER $getter $type);
            sockopt!(@SETTER $setter $type);
        )*
    };

    (@GETTER $getter:ident $type:ty) => {
        forward!($getter() -> zmq::Result<$type>);
    };
    (@GETTER _ $type:ty) => {};

    (@SETTER $setter:ident $type:ty) => {
        forward!($setter(value: $type) -> zmq::Result<()>);
    };
    (@SETTER _ $type:ty) => {};
}

impl Socket {
    forward! {
        bind(endpoint: &str) -> zmq::Result<()>;
        unbind(endpoint: &str) -> zmq::Result<()>;
        connect(endpoint: &str) -> zmq::Result<()>;
        disconnect(endpoint: &str) -> zmq::Result<()>;
        monitor(monitor_endpoint: &str, events: i32) -> zmq::Result<()>;
    }

    sockopt! {
        is_ipv6 set_ipv6 bool;
        is_immediate set_immediate bool;
        is_plain_server set_plain_server bool;
        is_conflate set_conflate bool;
        is_probe_router set_probe_router bool;
        is_router_mandatory set_router_mandatory bool;
        is_router_handover set_router_handover bool;
        is_curve_server set_curve_server bool;
        is_gssapi_server set_gssapi_server bool;
        is_gssapi_plaintext set_gssapi_plaintext bool;
        _ set_req_relaxed bool;
        _ set_req_correlate bool;
    }

    forward! {
        get_socket_type() -> zmq::Result<SocketType>;
        get_rcvmore() -> zmq::Result<bool>;
    }

    sockopt! {
        get_maxmsgsize set_maxmsgsize i64;
        get_sndhwm set_sndhwm i32;
        get_rcvhwm set_rcvhwm i32;
        get_affinity set_affinity u64;
        get_rate set_rate i32;
        get_recovery_ivl set_recovery_ivl i32;
        get_sndbuf set_sndbuf i32;
        get_rcvbuf set_rcvbuf i32;
        get_tos set_tos i32;
        get_linger set_linger i32;
        get_reconnect_ivl set_reconnect_ivl i32;
        get_reconnect_ivl_max set_reconnect_ivl_max i32;
        get_backlog set_backlog i32;

        get_fd _ RawFd;

        get_events _ PollEvents;

        get_multicast_hops set_multicast_hops i32;
        get_rcvtimeo set_rcvtimeo i32;
        get_sndtimeo set_sndtimeo i32;
        get_tcp_keepalive set_tcp_keepalive i32;
        get_tcp_keepalive_cnt set_tcp_keepalive_cnt i32;
        get_tcp_keepalive_idle set_tcp_keepalive_idle i32;
        get_tcp_keepalive_intvl set_tcp_keepalive_intvl i32;
        get_handshake_ivl set_handshake_ivl i32;
        _ set_identity &[u8];
        _ set_subscribe &[u8];
        _ set_unsubscribe &[u8];
        get_heartbeat_ivl set_heartbeat_ivl i32;
        get_heartbeat_ttl set_heartbeat_ttl i32;
        get_heartbeat_timeout set_heartbeat_timeout i32;
        get_connect_timeout set_connect_timeout i32;
    }

    forward! {
        get_identity() -> zmq::Result<Vec<u8>>;
        get_socks_proxy() -> zmq::Result<Result<String, Vec<u8>>>;
        get_mechanism() -> zmq::Result<Mechanism>;
        get_plain_username() -> zmq::Result<Result<String, Vec<u8>>>;
        get_plain_password() -> zmq::Result<Result<String, Vec<u8>>>;
        get_zap_domain() -> zmq::Result<Result<String, Vec<u8>>>;
        get_last_endpoint() -> zmq::Result<Result<String, Vec<u8>>>;
        get_curve_publickey() -> zmq::Result<Vec<u8>>;
        get_curve_secretkey() -> zmq::Result<Vec<u8>>;
        get_curve_serverkey() -> zmq::Result<Vec<u8>>;
        get_gssapi_principal() -> zmq::Result<Result<String, Vec<u8>>>;
        get_gssapi_service_principal() -> zmq::Result<Result<String, Vec<u8>>>;
    }

    sockopt! {
        _ set_socks_proxy Option<&str>;
        _ set_plain_username Option<&str>;
        _ set_plain_password Option<&str>;
        _ set_zap_domain &str;
        _ set_xpub_welcome_msg Option<&str>;
        _ set_xpub_verbose bool;

        _ set_curve_publickey &[u8];
        _ set_curve_secretkey &[u8];
        _ set_curve_serverkey &[u8];
        _ set_gssapi_principal &str;
        _ set_gssapi_service_principal &str;
    }
}
