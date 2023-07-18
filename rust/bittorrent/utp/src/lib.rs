//! uTorrent Transport Protocol (uTP)

mod bstream;
mod conn;
mod packet;
mod timestamp;

use std::time::Duration;

pub use crate::bstream::{UtpRecvStream, UtpSendStream, UtpStream};

g1_param::define!(
    /// Upper bound of the RTT timeout.
    // BEP 29 does not specify this, but it would be nice to have one.
    max_rtt_timeout: Duration = Duration::from_secs(8)
);

g1_param::define!(
    /// Timeout for appending a payload to the stream's incoming queue.
    recv_buffer_timeout: Duration = Duration::from_secs(1)
);

g1_param::define!(
    /// Limit on the number of times a packet can be resent.
    resend_limit: usize = 2
);
