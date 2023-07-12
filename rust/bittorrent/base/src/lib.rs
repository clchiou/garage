pub const PROTOCOL_ID: &[u8] = b"BitTorrent protocol";

pub const INFO_HASH_SIZE: usize = 20;
pub const PIECE_HASH_SIZE: usize = 20;

#[cfg(feature = "param")]
g1_param::define!(pub recv_buffer_capacity: usize = 65536);
#[cfg(feature = "param")]
g1_param::define!(pub send_buffer_capacity: usize = 65536);

#[cfg(feature = "param")]
g1_param::define!(pub payload_size_limit: usize = 65536);
