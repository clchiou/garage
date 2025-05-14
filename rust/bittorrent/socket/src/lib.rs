pub mod error;

mod handshake;
mod message;

use std::io::Error;
use std::time::Duration;

use snafu::prelude::*;

use g1_tokio::bstream::{StreamBuffer, StreamRecv, StreamSend};

use bittorrent_base::{Features, InfoHash, PeerId};

pub use message::Message;

g1_param::define!(
    handshake_timeout: Duration = Duration::from_secs(8);
    parse = g1_param::parse::duration;
);

#[derive(Debug)]
pub struct Socket<Stream> {
    stream: Stream,
    self_features: Features,
    peer_id: PeerId,
    peer_features: Features,
}

macro_rules! gen_handshake {
    ($handshake:ident) => {
        pub async fn $handshake(
            mut stream: Stream,
            info_hash: InfoHash,
            self_id: PeerId,
            self_features: Features,
            expect_peer_id: Option<PeerId>,
        ) -> Result<Self, Error> {
            let result = handshake::$handshake(
                &mut stream,
                info_hash,
                self_id,
                self_features,
                expect_peer_id,
            )
            .await;
            let (peer_id, peer_features) = match result {
                Ok(pair) => pair,
                Err(error) => {
                    if let Err(error) = stream.shutdown().await {
                        tracing::warn!(%error, "peer stream shutdown error");
                    }
                    return Err(error);
                }
            };
            Ok(Self {
                stream,
                self_features,
                peer_id,
                peer_features,
            })
        }
    };
}

impl<Stream> Socket<Stream>
where
    Stream: StreamRecv<Error = Error> + StreamSend<Error = Error> + Send,
{
    gen_handshake!(connect);
    gen_handshake!(accept);

    pub fn self_features(&self) -> Features {
        self.self_features
    }

    pub fn peer_id(&self) -> PeerId {
        self.peer_id.clone()
    }

    pub fn peer_features(&self) -> Features {
        self.peer_features
    }

    fn check_features(&self, message: &Message) -> Result<(), error::Error> {
        ensure!(
            message.get_feature(self.self_features).unwrap_or(true),
            error::ExpectFeatureEnabledSnafu {
                message: message.clone(),
            },
        );
        ensure!(
            message.get_feature(self.peer_features).unwrap_or(true),
            error::ExpectFeatureSupportedSnafu {
                message: message.clone(),
            },
        );
        Ok(())
    }

    pub async fn recv(&mut self) -> Result<Message, Error> {
        let message = Message::recv_from(&mut self.stream).await?;
        self.check_features(&message)?;
        Ok(message)
    }

    pub async fn send(&mut self, message: Message) -> Result<(), Error> {
        self.send_many([message].into_iter()).await
    }

    pub async fn send_many(
        &mut self,
        messages: impl Iterator<Item = Message>,
    ) -> Result<(), Error> {
        for message in messages {
            if let Err(error) = self.check_features(&message) {
                panic!("send_many: {error}"); // `panic!` because it is our fault.
            }
            message.encode(&mut *self.stream.send_buffer());
        }
        self.stream.send_all().await
    }

    pub async fn shutdown(&mut self) -> Result<(), Error> {
        self.stream.shutdown().await
    }
}

#[cfg(feature = "test_harness")]
mod test_harness {
    use tokio::io::DuplexStream;

    use g1_tokio::io::Stream;

    use super::*;

    impl Socket<Stream<DuplexStream>> {
        pub fn new_mock(
            stream: Stream<DuplexStream>,
            self_features: Features,
            peer_id: PeerId,
            peer_features: Features,
        ) -> Self {
            Self {
                stream,
                self_features,
                peer_id,
                peer_features,
            }
        }
    }
}
