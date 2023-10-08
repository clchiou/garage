use std::io::Error;
use std::net::SocketAddr;

use bytes::Bytes;

use g1_futures::stream;

//
// Implementer's Notes: `fork` cannot send an input item to multiple forks.  Currently, all errors
// and non-recognizable payloads (effectively errors) are directed to the last fork.
//

g1_param::define!(dht_queue_size: usize = 256);
g1_param::define!(utp_queue_size: usize = 256);
g1_param::define!(error_queue_size: usize = 32);

pub type Fork<Stream> = stream::Fork<Stream, fn(&Item) -> bool, Item>;
type Item = Result<(SocketAddr, Bytes), Error>;

// TODO: Support BEP 15 UDP Tracker Protocol.
pub fn fork<Stream>(stream: Stream) -> (Fork<Stream>, Fork<Stream>, Fork<Stream>) {
    <[Fork<Stream>; 3]>::into(stream::fork(
        stream,
        [
            (is_dht, *dht_queue_size()),
            (is_utp, *utp_queue_size()),
            (is_error, *error_queue_size()),
        ],
    ))
}

fn is_dht(item: &Item) -> bool {
    // All DHT messages must begin with the ASCII letter 'd' as they are Bencode dictionaries.
    matches!(item, Ok((_, payload)) if payload[0] == b'd')
}

fn is_utp(item: &Item) -> bool {
    matches!(item, Ok((_, payload)) if (payload[0] & 0xf0) <= 0x40 && (payload[0] & 0x0f) == 0x01)
}

fn is_error(_: &Item) -> bool {
    true
}
