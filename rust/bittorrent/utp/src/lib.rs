//! uTorrent Transport Protocol (uTP)

#![feature(io_error_other)]
#![feature(result_option_inspect)]
#![feature(try_blocks)]
#![cfg_attr(test, feature(assert_matches))]
#![cfg_attr(test, feature(duration_constants))]

mod bstream;
mod conn;
mod mtu;
mod packet;
mod socket;
mod timestamp;

use std::time::Duration;

pub use crate::bstream::{UtpRecvStream, UtpSendStream, UtpStream};
pub use crate::socket::UtpSocket;

g1_param::define!(recv_window_size: usize = 65536);
g1_param::define!(send_window_size_limit: usize = 65536);
g1_param::define!(packet_size: usize = 150);

g1_param::define!(connect_timeout: Duration = Duration::from_secs(2));
g1_param::define!(accept_timeout: Duration = Duration::from_secs(2));

g1_param::define!(congestion_control_target: Duration = Duration::from_millis(100));
g1_param::define!(max_congestion_window_increase_per_rtt: usize = 3000);

g1_param::define!(
    /// Upper bound of the RTT timeout.
    // BEP 29 does not specify this, but it would be nice to have one.
    max_rtt_timeout: Duration = Duration::from_secs(8)
);

g1_param::define!(
    /// Timeout for receiving any packet.
    recv_idle_timeout: Duration = Duration::from_secs(1)
);
g1_param::define!(
    /// Timeout for appending a payload to the stream's incoming queue.
    recv_buffer_timeout: Duration = Duration::from_secs(1)
);
g1_param::define!(
    /// Timeout for when the remaining data packets arrive after the stream receives the finish
    /// packet.
    recv_grace_period: Duration = Duration::from_secs(4)
);

g1_param::define!(
    /// Limit on the number of times a packet can be resent.
    resend_limit: usize = 2
);

g1_param::define!(path_mtu_max_probe_size: usize = 2400);
g1_param::define!(path_mtu_reprobe_period: Duration = Duration::from_secs(60));
g1_param::define!(path_mtu_icmp_reply_timeout: Duration = Duration::from_secs(2));

g1_param::define!(
    /// Timeout for the socket actor shutdown.
    grace_period: Duration = Duration::from_secs(2)
);