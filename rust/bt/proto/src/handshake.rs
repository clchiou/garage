use std::io::{self, ErrorKind};
use std::time::Duration;

use bitvec::prelude::*;
use snafu::prelude::*;
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt};
use tokio::time;

use bt_base::info_hash::INFO_HASH_SIZE;
use bt_base::peer_id::PEER_ID_SIZE;
use bt_base::{Features, InfoHash, PeerId};

#[derive(Clone, Debug)]
pub struct Handshaker<F> {
    self_id: PeerId,
    self_features: Features,
    match_info_hash: F,
    timeout: Duration,
}

#[derive(Debug, Snafu)]
pub enum Error {
    #[snafu(display("io error: {source}"))]
    Io { source: io::Error },

    #[snafu(display("info hash not matched: {info_hash}"))]
    NotMatched { info_hash: InfoHash },

    #[snafu(display(
        "expect protocol id == {}: {}",
        PROTOCOL_ID.escape_ascii(),
        protocol_id.escape_ascii(),
    ))]
    ProtocolId {
        protocol_id: [u8; PROTOCOL_ID.len()],
    },
    #[snafu(display("expect protocol id size == {PROTOCOL_ID_SIZE}: {size}"))]
    ProtocolIdSize { size: u8 },

    #[snafu(display("handshake timeout"))]
    Timeout,
}

// For convenience.
impl From<Error> for io::Error {
    fn from(error: Error) -> Self {
        match error {
            Error::Io { source } => source,
            Error::Timeout => Self::new(ErrorKind::TimedOut, error),
            _ => Self::other(error),
        }
    }
}

impl<F> Handshaker<F> {
    pub fn new(self_id: PeerId, self_features: Features, match_info_hash: F) -> Self {
        Self {
            self_id,
            self_features,
            match_info_hash,
            // TODO: Make this configurable.
            timeout: Duration::from_secs(8),
        }
    }
}

impl<F> Handshaker<F>
where
    F: Fn(InfoHash) -> bool,
{
    pub async fn accept<T>(&self, stream: T) -> Result<(PeerId, Features), Error>
    where
        T: AsyncRead + AsyncWrite + Unpin,
    {
        time::timeout(self.timeout, self.accept_forever(stream))
            .await
            .map_err(|_| Error::Timeout)?
    }

    pub async fn accept_forever<T>(&self, mut stream: T) -> Result<(PeerId, Features), Error>
    where
        T: AsyncRead + AsyncWrite + Unpin,
    {
        let (info_hash, peer_features) = recv_handshake(&mut stream, &self.match_info_hash).await?;
        send_handshake(&mut stream, &info_hash, self.self_features).await?;

        send_id(&mut stream, &self.self_id).await?;
        let peer_id = recv_id(&mut stream).await?;

        Ok((peer_id, peer_features))
    }
}

impl<F> Handshaker<F> {
    pub async fn connect<T>(
        &self,
        stream: T,
        info_hash: InfoHash,
    ) -> Result<(PeerId, Features), Error>
    where
        T: AsyncRead + AsyncWrite + Unpin,
    {
        time::timeout(self.timeout, self.connect_forever(stream, info_hash))
            .await
            .map_err(|_| Error::Timeout)?
    }

    pub async fn connect_forever<T>(
        &self,
        mut stream: T,
        info_hash: InfoHash,
    ) -> Result<(PeerId, Features), Error>
    where
        T: AsyncRead + AsyncWrite + Unpin,
    {
        send_handshake(&mut stream, &info_hash, self.self_features).await?;
        let (_, peer_features) = recv_handshake(&mut stream, |x| x == info_hash).await?;

        send_id(&mut stream, &self.self_id).await?;
        let peer_id = recv_id(&mut stream).await?;

        Ok((peer_id, peer_features))
    }
}

async fn recv_handshake<T, F>(
    mut stream: T,
    match_info_hash: F,
) -> Result<(InfoHash, Features), Error>
where
    T: AsyncRead + Unpin,
    F: Fn(InfoHash) -> bool,
{
    let size = stream.read_u8().await.context(IoSnafu)?;
    ensure!(size == PROTOCOL_ID_SIZE, ProtocolIdSizeSnafu { size });

    let mut protocol_id = [0u8; PROTOCOL_ID.len()];
    stream.read_exact(&mut protocol_id).await.context(IoSnafu)?;
    ensure!(protocol_id == PROTOCOL_ID, ProtocolIdSnafu { protocol_id });

    let mut reserved = [0u8; RESERVED_SIZE];
    stream.read_exact(&mut reserved).await.context(IoSnafu)?;
    let peer_features = to_features(&reserved);

    clear_known_bits(&mut reserved);
    if reserved != [0u8; RESERVED_SIZE] {
        tracing::warn!(?reserved, "unknown reserved bits");
    }

    let mut info_hash = [0u8; INFO_HASH_SIZE];
    stream.read_exact(&mut info_hash).await.context(IoSnafu)?;
    let info_hash = InfoHash::from(info_hash);
    ensure!(
        match_info_hash(info_hash.clone()),
        NotMatchedSnafu { info_hash },
    );

    Ok((info_hash, peer_features))
}

async fn send_handshake<T>(
    mut stream: T,
    info_hash: &InfoHash,
    self_features: Features,
) -> Result<(), Error>
where
    T: AsyncWrite + Unpin,
{
    let result: Result<_, _> = try {
        stream.write_u8(PROTOCOL_ID_SIZE).await?;
        stream.write_all(PROTOCOL_ID).await?;
        stream.write_all(&to_reserved(self_features)).await?;
        stream.write_all(info_hash.as_ref()).await?;
        stream.flush().await?;
    };
    result.context(IoSnafu)
}

async fn recv_id<T>(mut stream: T) -> Result<PeerId, Error>
where
    T: AsyncRead + Unpin,
{
    let mut peer_id = [0u8; PEER_ID_SIZE];
    stream.read_exact(&mut peer_id).await.context(IoSnafu)?;
    Ok(peer_id.into())
}

async fn send_id<T>(mut stream: T, self_id: &PeerId) -> Result<(), Error>
where
    T: AsyncWrite + Unpin,
{
    let result: Result<_, _> = try {
        stream.write_all(self_id.as_ref()).await?;
        stream.flush().await?;
    };
    result.context(IoSnafu)
}

//
// Handshake Message
//

const PROTOCOL_ID: &[u8] = b"BitTorrent protocol";
const PROTOCOL_ID_SIZE: u8 = PROTOCOL_ID.len() as u8;

type Reserved = [u8; RESERVED_SIZE];
type ReservedBits = BitSlice<u8, Msb0>;

const RESERVED_SIZE: usize = 8;

const RESERVED_AZUREUS_MESSAGING: usize = 0;
const RESERVED_LOCATION_AWARE: usize = 20;
const RESERVED_EXTENSION: usize = 43; // BEP 10

// BEP 30 does not specify the setting of reserved bit 44, and [libtorrent] appears to be in
// violation of the BEP.
// [libtorrent]: https://github.com/arvidn/libtorrent/commit/84a513bffbd7b3b6edf5d28c09892388d59e201a#diff-68c1bba05514f22a8cfc3a4f062f6ec8714f0942a359d7c4a65be32d1b3dab61R792
const RESERVED_MERKLE_TREE: usize = 44;

const RESERVED_EXTENSION_NEGOTIATION_0: usize = 46;
const RESERVED_EXTENSION_NEGOTIATION_1: usize = 47;
const RESERVED_HYBRID: usize = 59; // BEP 52
const RESERVED_NAT_TRAVERSAL: usize = 60;
const RESERVED_FAST: usize = 61; // BEP 6
const RESERVED_XBT_PEER_EXCHANGE: usize = 62;
const RESERVED_DHT: usize = 63; // BEP 5

const RESERVED_OFFSETS: &[usize] = &[
    RESERVED_AZUREUS_MESSAGING,
    RESERVED_LOCATION_AWARE,
    RESERVED_EXTENSION,
    RESERVED_MERKLE_TREE,
    RESERVED_EXTENSION_NEGOTIATION_0,
    RESERVED_EXTENSION_NEGOTIATION_1,
    RESERVED_HYBRID,
    RESERVED_NAT_TRAVERSAL,
    RESERVED_FAST,
    RESERVED_XBT_PEER_EXCHANGE,
    RESERVED_DHT,
];

fn to_reserved(features: Features) -> Reserved {
    let Features {
        dht,
        fast,
        extension,
    } = features;
    let mut reserved = [0u8; RESERVED_SIZE];
    let bits: &mut ReservedBits = reserved.view_bits_mut();
    bits.set(RESERVED_DHT, dht);
    bits.set(RESERVED_FAST, fast);
    bits.set(RESERVED_EXTENSION, extension);
    reserved
}

fn to_features(reserved: &Reserved) -> Features {
    let bits: &ReservedBits = reserved.view_bits();
    Features {
        dht: bits[RESERVED_DHT],
        fast: bits[RESERVED_FAST],
        extension: bits[RESERVED_EXTENSION],
    }
}

fn clear_known_bits(reserved: &mut Reserved) {
    let bits: &mut ReservedBits = reserved.view_bits_mut();
    for offset in RESERVED_OFFSETS {
        bits.set(*offset, false);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn features() {
        let zero = Features {
            dht: false,
            fast: false,
            extension: false,
        };
        for features in [
            zero,
            Features { dht: true, ..zero },
            Features { fast: true, ..zero },
            Features {
                extension: true,
                ..zero
            },
            Features {
                dht: true,
                fast: true,
                extension: true,
            },
        ] {
            assert_eq!(to_features(&to_reserved(features)), features);
        }
    }
}
