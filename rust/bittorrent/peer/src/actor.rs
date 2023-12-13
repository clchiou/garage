use std::collections::{HashSet, VecDeque};
use std::io::{Error, ErrorKind};
use std::sync::{Arc, Mutex};

use tokio::{
    sync::{
        mpsc::{error::TrySendError, UnboundedReceiver},
        Notify,
    },
    time::{self, Interval},
};

use g1_base::sync::MutexExt;
use g1_tokio::bstream::{StreamRecv, StreamSend};

use bittorrent_base::{BlockDesc, PieceIndex};
use bittorrent_extension::{ExtensionIdMap, Message as ExtensionMessage};
use bittorrent_socket::{Message, Socket};

use crate::{
    chan::{Endpoint, Sends},
    error,
    incoming::{self, Reject, Response},
    outgoing,
    state::ConnStateLower,
    Full, Possession,
};

#[derive(Debug)]
pub(crate) struct Actor<Stream> {
    exit: Arc<Notify>,

    socket: Socket<Stream>,

    extension_ids: Arc<Mutex<ExtensionIdMap>>,

    conn_state: ConnStateLower,
    incomings: incoming::Queue,
    outgoings: outgoing::QueueLower,
    message_recv: UnboundedReceiver<Message>,

    recv_keep_alive_interval: Interval,
    send_keep_alive_interval: Interval,

    peer_allowed_fast: HashSet<PieceIndex>,

    peer_endpoint: Endpoint,
    sends: Sends,
}

macro_rules! try_send {
    ($self:ident, $queue:ident, $value:expr $(,)?) => {
        if let Err(error) = $self.sends.$queue.try_send($value) {
            let queue = stringify!($queue);
            let queue = &queue[..queue.len() - "_send".len()];
            match error {
                TrySendError::Full(_) => tracing::warn!(queue, "peer queue is full"),
                TrySendError::Closed(_) => tracing::warn!(queue, "peer queue is closed"),
            }
        }
    };
}

impl<Stream> Actor<Stream>
where
    Stream: StreamRecv<Error = Error> + StreamSend<Error = Error> + Send,
{
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn new(
        exit: Arc<Notify>,
        socket: Socket<Stream>,
        extension_ids: Arc<Mutex<ExtensionIdMap>>,
        conn_state: ConnStateLower,
        incomings: incoming::Queue,
        outgoings: outgoing::QueueLower,
        message_recv: UnboundedReceiver<Message>,
        peer_endpoint: Endpoint,
        sends: Sends,
    ) -> Self {
        Self {
            exit,
            socket,
            extension_ids,
            conn_state,
            incomings,
            outgoings,
            message_recv,
            recv_keep_alive_interval: time::interval(*crate::recv_keep_alive_timeout()),
            send_keep_alive_interval: time::interval(*crate::send_keep_alive_timeout()),
            peer_allowed_fast: HashSet::new(),
            peer_endpoint,
            sends,
        }
    }

    pub(crate) async fn run(mut self) -> Result<(), Error> {
        self.recv_keep_alive_interval.reset();
        self.send_keep_alive_interval.reset();
        loop {
            tokio::select! {
                _ = self.exit.notified() => {
                    break;
                }

                message = self.socket.recv() => {
                    self.handle_recv(message?).await?;
                }

                value = self.conn_state.self_choking.updated() => {
                    match value {
                        Ok(value) => self.handle_self_choking(value).await?,
                        Err(_) => break,
                    }
                }
                value = self.conn_state.self_interested.updated() => {
                    match value {
                        Ok(value) => self.handle_self_interested(value).await?,
                        Err(_) => break,
                    }
                }

                (desc, response) = self.incomings.dequeue() => {
                    self.handle_incoming(desc, response).await?;
                }

                Some(desc) = self.outgoings.expired() => {
                    self.handle_expired(desc);
                }
                desc = self.outgoings.new_recv.recv() => {
                    match desc {
                        Some(desc) => self.handle_new(desc).await?,
                        None => break,
                    }
                }
                desc = self.outgoings.cancel_recv.recv() => {
                    match desc {
                        Some(desc) => self.handle_cancel(desc).await?,
                        None => break,
                    }
                }

                message = self.message_recv.recv() => {
                    match message {
                        Some(message) => self.send(message).await?,
                        None => break,
                    }
                }

                _ = self.recv_keep_alive_interval.tick() => {
                    return Err(Error::new(ErrorKind::TimedOut, error::Error::KeepAliveTimeout));
                }
                _ = self.send_keep_alive_interval.tick() => {
                    self.send(Message::KeepAlive).await?;
                }
            }
        }
        self.socket.shutdown().await
    }

    async fn handle_recv(&mut self, message: Message) -> Result<(), Error> {
        self.recv_keep_alive_interval.reset();

        match message {
            Message::KeepAlive => Ok(()),

            Message::Choke => {
                // There is a delay between when the peer decides to choke us and when we receive
                // the choke message.  The requests that are sent during this delay might get
                // silently dropped by the peer.  For now, we use the request timeout to detect
                // this scenario.
                self.conn_state.peer_choking.set(true);
                Ok(())
            }
            Message::Unchoke => {
                self.conn_state.peer_choking.set(false);
                self.send_requests(self.outgoings.take_choke()).await
            }
            Message::Interested => {
                self.conn_state.peer_interested.set(true);
                try_send!(self, interested_send, self.peer_endpoint);
                Ok(())
            }
            Message::NotInterested => {
                self.conn_state.peer_interested.set(false);
                Ok(())
            }

            Message::Request(desc) => {
                // TODO: Add `self_allowed_fast` and check whether the request is allowed.
                if self.conn_state.self_choking.get() {
                    tracing::debug!(?desc, "reject request because we are choking peer");
                    if self.socket.self_features().fast && self.socket.peer_features().fast {
                        self.send(Message::Reject(desc)).await?;
                    }
                    return Ok(());
                }
                match self.incomings.enqueue(desc) {
                    Ok(Some(response_send)) => try_send!(
                        self,
                        request_send,
                        (self.peer_endpoint, desc, response_send),
                    ),
                    Ok(None) => tracing::debug!(?desc, "ignore duplicated request"),
                    Err(Full) => {
                        tracing::warn!(?desc, "incoming queue is full");
                        if self.socket.self_features().fast && self.socket.peer_features().fast {
                            self.send(Message::Reject(desc)).await?;
                        }
                    }
                }
                Ok(())
            }
            Message::Cancel(desc) => {
                self.incomings.cancel(desc);
                Ok(())
            }

            Message::Have(index) => {
                try_send!(
                    self,
                    possession_send,
                    (self.peer_endpoint, Possession::Have(index)),
                );
                Ok(())
            }
            Message::Bitfield(bitfield) => {
                try_send!(
                    self,
                    possession_send,
                    (self.peer_endpoint, Possession::Bitfield(bitfield)),
                );
                Ok(())
            }
            Message::HaveAll => {
                try_send!(
                    self,
                    possession_send,
                    (self.peer_endpoint, Possession::HaveAll),
                );
                Ok(())
            }
            Message::HaveNone => {
                try_send!(
                    self,
                    possession_send,
                    (self.peer_endpoint, Possession::HaveNone),
                );
                Ok(())
            }

            Message::Suggest(index) => {
                try_send!(self, suggest_send, (self.peer_endpoint, index));
                Ok(())
            }

            Message::AllowedFast(index) => {
                self.peer_allowed_fast.insert(index);
                try_send!(self, allowed_fast_send, (self.peer_endpoint, index));
                Ok(())
            }

            Message::Piece(desc, payload) => {
                match self.outgoings.dequeue(desc) {
                    Some(response_send) => {
                        let _ = response_send.send(payload);
                    }
                    None => try_send!(self, block_send, (self.peer_endpoint, (desc, payload))),
                }
                Ok(())
            }
            Message::Reject(desc) => {
                tracing::debug!(?desc, "request is rejected");
                let _ = self.outgoings.dequeue(desc);
                Ok(())
            }

            Message::Port(port) => {
                try_send!(self, port_send, (self.peer_endpoint, port));
                Ok(())
            }

            Message::Extended(id, payload) => {
                let message = bittorrent_extension::decode(id, payload).map_err(Error::other)?;
                if let ExtensionMessage::Handshake(handshake) = message.deref() {
                    self.extension_ids.must_lock().update(handshake);
                }
                try_send!(self, extension_send, (self.peer_endpoint, message));
                Ok(())
            }
        }
    }

    async fn handle_self_choking(&mut self, value: bool) -> Result<(), Error> {
        self.send(if value {
            Message::Choke
        } else {
            Message::Unchoke
        })
        .await
    }

    async fn handle_self_interested(&mut self, value: bool) -> Result<(), Error> {
        self.send(if value {
            Message::Interested
        } else {
            Message::NotInterested
        })
        .await
    }

    async fn handle_incoming(&mut self, desc: BlockDesc, response: Response) -> Result<(), Error> {
        self.send(match response {
            Ok(block) => Message::Piece(desc, block),
            Err(Reject) => Message::Reject(desc),
        })
        .await
    }

    fn handle_expired(&mut self, desc: BlockDesc) {
        if self.outgoings.dequeue(desc).is_some() {
            tracing::warn!(?desc, "peer block request timeout");
        }
    }

    async fn handle_new(&mut self, desc: BlockDesc) -> Result<(), Error> {
        if !self.conn_state.peer_choking.get() || self.peer_allowed_fast.contains(&desc.0 .0) {
            self.send(Message::Request(desc)).await
        } else {
            self.outgoings.push_choke(desc);
            self.send(Message::Interested).await
        }
    }

    async fn handle_cancel(&mut self, desc: BlockDesc) -> Result<(), Error> {
        self.send(Message::Cancel(desc)).await
    }

    async fn send_requests(&mut self, requests: VecDeque<BlockDesc>) -> Result<(), Error> {
        if requests.is_empty() {
            return Ok(());
        }
        self.send_keep_alive_interval.reset();
        self.socket
            .send_many(requests.into_iter().map(Message::Request))
            .await
    }

    async fn send(&mut self, message: Message) -> Result<(), Error> {
        self.send_keep_alive_interval.reset();
        self.socket.send(message).await
    }
}

#[cfg(test)]
mod test_harness {
    use std::time::Duration;

    use tokio::{io::DuplexStream, sync::mpsc};

    use g1_tokio::io::Stream;

    use bittorrent_base::{Features, PeerId, PEER_ID_SIZE};

    use crate::{
        chan::{self, Recvs},
        incoming, outgoing,
        state::{self, ConnStateUpper},
    };

    use super::*;

    impl Actor<Stream<DuplexStream>> {
        pub fn new_mock() -> (
            Self,
            DuplexStream,
            Arc<Notify>,
            ConnStateUpper,
            outgoing::QueueUpper,
            mpsc::UnboundedSender<Message>,
            Recvs,
        ) {
            let exit = Arc::new(Notify::new());
            let (stream, mock) = Stream::new_mock(4096);
            let (conn_state_upper, conn_state_lower) = state::new_conn_state();
            let (outgoings_upper, outgoings_lower) = outgoing::new_queue(10, Duration::ZERO);
            let (message_send, message_recv) = mpsc::unbounded_channel();
            let (recvs, sends) = chan::new_channels();
            let actor = Actor::new(
                exit.clone(),
                Socket::new_mock(
                    stream,
                    Features::new(true, true, true),
                    PeerId::new([0u8; PEER_ID_SIZE]),
                    Features::new(true, true, true),
                ),
                Arc::new(Mutex::new(ExtensionIdMap::new())),
                conn_state_lower,
                incoming::Queue::new(10),
                outgoings_lower,
                message_recv,
                "127.0.0.1:8000".parse().unwrap(),
                sends,
            );
            (
                actor,
                mock,
                exit,
                conn_state_upper,
                outgoings_upper,
                message_send,
                recvs,
            )
        }
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use bytes::Bytes;
    use hex_literal::hex;
    use tokio::io::{AsyncReadExt, DuplexStream};

    use bittorrent_base::BlockOffset;
    use bittorrent_extension::Enabled;

    use super::*;

    const DESC3: BlockDesc = BlockDesc(BlockOffset(PieceIndex(1), 2), 3);
    const DESC11: BlockDesc = BlockDesc(BlockOffset(PieceIndex(1), 2), 11);

    async fn assert_mock(mut mock: DuplexStream, expect: &[u8]) {
        let mut data = Vec::new();
        mock.read_to_end(&mut data).await.unwrap();
        assert_eq!(data, expect);
    }

    #[tokio::test]
    async fn handle_recv_keep_alive() {
        let (mut actor, mock, ..) = Actor::new_mock();
        assert_matches!(actor.handle_recv(Message::KeepAlive).await, Ok(()));
        drop(actor);
        assert_mock(mock, &[]).await;
    }

    #[tokio::test]
    async fn handle_recv_peer_choking() {
        {
            let (mut actor, mock, ..) = Actor::new_mock();
            assert_eq!(actor.conn_state.peer_choking.get(), true);

            assert_matches!(actor.handle_recv(Message::Unchoke).await, Ok(()));
            assert_eq!(actor.conn_state.peer_choking.get(), false);

            assert_matches!(actor.handle_recv(Message::Choke).await, Ok(()));
            assert_eq!(actor.conn_state.peer_choking.get(), true);

            drop(actor);
            assert_mock(mock, &[]).await;
        }
        {
            let (mut actor, mock, _, _, outgoings, ..) = Actor::new_mock();
            let _response_recv = outgoings.enqueue(DESC3).unwrap().unwrap();
            actor.outgoings.push_choke(DESC3);
            actor.outgoings.assert(&[DESC3], 3, &[DESC3], &[DESC3]);

            assert_matches!(actor.handle_recv(Message::Unchoke).await, Ok(()));
            actor.outgoings.assert(&[DESC3], 3, &[DESC3], &[]);

            drop(actor);
            assert_mock(mock, &hex!("0000000d 06 00000001 00000002 00000003")).await;
        }
    }

    #[tokio::test]
    async fn handle_recv_peer_interested() {
        let (mut actor, mock, .., mut recvs) = Actor::new_mock();
        assert_eq!(actor.conn_state.peer_interested.get(), false);

        assert_matches!(actor.handle_recv(Message::Interested).await, Ok(()));
        assert_eq!(actor.conn_state.peer_interested.get(), true);
        assert_matches!(recvs.interested_recv.recv().await, Some(_));

        assert_matches!(actor.handle_recv(Message::NotInterested).await, Ok(()));
        assert_eq!(actor.conn_state.peer_interested.get(), false);
        assert_matches!(recvs.interested_recv.try_recv(), Err(_));

        drop(actor);
        assert_mock(mock, &[]).await;
    }

    #[tokio::test]
    async fn handle_recv_request() {
        {
            let (mut actor, mock, .., mut recvs) = Actor::new_mock();
            assert_matches!(actor.handle_recv(Message::Request(DESC3)).await, Ok(()));
            actor.incomings.assert(&[], 0);
            assert_matches!(recvs.request_recv.try_recv(), Err(_));
            drop(actor);
            assert_mock(mock, &hex!("0000000d 10 00000001 00000002 00000003")).await;
        }
        {
            let (mut actor, mock, _, conn_state, .., mut recvs) = Actor::new_mock();
            conn_state.self_choking.set(false);

            assert_matches!(actor.handle_recv(Message::Request(DESC3)).await, Ok(()));
            actor.incomings.assert(&[DESC3], 3);
            assert_matches!(recvs.request_recv.recv().await, Some((_, desc, _)) if desc == DESC3);

            for _ in 0..3 {
                assert_matches!(actor.handle_recv(Message::Request(DESC3)).await, Ok(()));
                actor.incomings.assert(&[DESC3], 3);
                assert_matches!(recvs.request_recv.try_recv(), Err(_));
            }

            drop(actor);
            assert_mock(mock, &[]).await;
        }
        {
            let (mut actor, mock, _, conn_state, .., mut recvs) = Actor::new_mock();
            conn_state.self_choking.set(false);

            assert_matches!(actor.handle_recv(Message::Request(DESC11)).await, Ok(()));
            actor.incomings.assert(&[], 0);
            assert_matches!(recvs.request_recv.try_recv(), Err(_));

            drop(actor);
            assert_mock(mock, &hex!("0000000d 10 00000001 00000002 0000000b")).await;
        }
    }

    #[tokio::test]
    async fn handle_recv_cancel() {
        let (mut actor, mock, ..) = Actor::new_mock();
        let _response_send = actor.incomings.enqueue(DESC3).unwrap().unwrap();
        actor.incomings.assert(&[DESC3], 3);

        assert_matches!(actor.handle_recv(Message::Cancel(DESC3)).await, Ok(()));
        actor.incomings.assert(&[], 0);

        drop(actor);
        assert_mock(mock, &[]).await;
    }

    #[tokio::test]
    async fn handle_recv_possession() {
        for (message, expect) in [
            (Message::Have(1.into()), Possession::Have(1.into())),
            (
                Message::Bitfield(Bytes::from_static(&hex!("deadbeef"))),
                Possession::Bitfield(Bytes::from_static(&hex!("deadbeef"))),
            ),
            (Message::HaveAll, Possession::HaveAll),
            (Message::HaveNone, Possession::HaveNone),
        ] {
            let (mut actor, mock, .., mut recvs) = Actor::new_mock();
            assert_matches!(actor.handle_recv(message).await, Ok(()));
            assert_matches!(
                recvs.possession_recv.recv().await,
                Some((_, possession)) if possession == expect,
            );
            drop(actor);
            assert_mock(mock, &[]).await;
        }
    }

    #[tokio::test]
    async fn handle_recv_suggest() {
        let (mut actor, mock, .., mut recvs) = Actor::new_mock();
        assert_matches!(actor.handle_recv(Message::Suggest(1.into())).await, Ok(()));
        assert_matches!(recvs.suggest_recv.recv().await, Some((_, index)) if index == 1.into());
        drop(actor);
        assert_mock(mock, &[]).await;
    }

    #[tokio::test]
    async fn handle_recv_allowed_fast() {
        let (mut actor, mock, .., mut recvs) = Actor::new_mock();
        assert_eq!(actor.peer_allowed_fast, HashSet::new());

        assert_matches!(
            actor.handle_recv(Message::AllowedFast(1.into())).await,
            Ok(())
        );
        assert_matches!(
            recvs.allowed_fast_recv.recv().await,
            Some((_, index)) if index == 1.into(),
        );
        assert_eq!(actor.peer_allowed_fast, HashSet::from([1.into()]));

        for _ in 0..3 {
            assert_matches!(
                actor.handle_recv(Message::AllowedFast(1.into())).await,
                Ok(())
            );
            assert_matches!(
                recvs.allowed_fast_recv.recv().await,
                Some((_, index)) if index == 1.into(),
            );
            assert_eq!(actor.peer_allowed_fast, HashSet::from([1.into()]));
        }

        assert_matches!(recvs.allowed_fast_recv.try_recv(), Err(_));

        drop(actor);
        assert_mock(mock, &[]).await;
    }

    #[tokio::test]
    async fn handle_recv_piece() {
        {
            let (mut actor, mock, _, _, outgoings, .., mut recvs) = Actor::new_mock();
            let response_recv = outgoings.enqueue(DESC3).unwrap().unwrap();
            actor.outgoings.assert(&[DESC3], 3, &[DESC3], &[]);

            assert_matches!(
                actor
                    .handle_recv(Message::Piece(DESC3, Bytes::from_static(&hex!("aabbcc"))))
                    .await,
                Ok(()),
            );
            actor.outgoings.assert(&[], 0, &[DESC3], &[]);
            assert_matches!(
                response_recv.await,
                Ok(payload) if payload == hex!("aabbcc").as_slice(),
            );
            assert_matches!(recvs.block_recv.try_recv(), Err(_));

            drop(actor);
            assert_mock(mock, &[]).await;
        }
        {
            let (mut actor, mock, .., mut recvs) = Actor::new_mock();
            actor.outgoings.assert(&[], 0, &[], &[]);

            assert_matches!(
                actor
                    .handle_recv(Message::Piece(DESC3, Bytes::from_static(&hex!("aabbcc"))))
                    .await,
                Ok(()),
            );
            actor.outgoings.assert(&[], 0, &[], &[]);
            assert_matches!(
                recvs.block_recv.recv().await,
                Some((_, (desc, payload))) if desc == DESC3 && payload == hex!("aabbcc").as_slice(),
            );

            drop(actor);
            assert_mock(mock, &[]).await;
        }
    }

    #[tokio::test]
    async fn handle_recv_reject() {
        let (mut actor, mock, _, _, outgoings, ..) = Actor::new_mock();
        let _response_recv = outgoings.enqueue(DESC3).unwrap().unwrap();
        actor.outgoings.assert(&[DESC3], 3, &[DESC3], &[]);

        assert_matches!(actor.handle_recv(Message::Reject(DESC3)).await, Ok(()));
        actor.outgoings.assert(&[], 0, &[DESC3], &[]);

        drop(actor);
        assert_mock(mock, &[]).await;
    }

    #[tokio::test]
    async fn handle_recv_port() {
        let (mut actor, mock, .., mut recvs) = Actor::new_mock();
        assert_matches!(actor.handle_recv(Message::Port(1234)).await, Ok(()));
        assert_matches!(recvs.port_recv.recv().await, Some((_, 1234)));
        drop(actor);
        assert_mock(mock, &[]).await;
    }

    #[tokio::test]
    async fn handle_recv_extended() {
        let (mut actor, mock, .., mut recvs) = Actor::new_mock();
        assert_eq!(
            actor.extension_ids.must_lock().peer_extensions(),
            Enabled::new(false, false),
        );
        assert_matches!(
            actor
                .handle_recv(Message::Extended(
                    0,
                    Bytes::from_static(b"d1:md11:ut_metadatai99eee"),
                ))
                .await,
            Ok(()),
        );
        assert_matches!(
            recvs.extension_recv.recv().await,
            Some((_, message)) if matches!(message.deref(), ExtensionMessage::Handshake(_)),
        );
        assert_eq!(
            actor.extension_ids.must_lock().peer_extensions(),
            Enabled::new(true, false),
        );
        drop(actor);
        assert_mock(mock, &[]).await;
    }

    #[tokio::test]
    async fn handle_self_choking() {
        {
            let (mut actor, mock, ..) = Actor::new_mock();
            assert_matches!(actor.handle_self_choking(true).await, Ok(()));
            drop(actor);
            assert_mock(mock, &hex!("00000001 00")).await;
        }
        {
            let (mut actor, mock, ..) = Actor::new_mock();
            assert_matches!(actor.handle_self_choking(false).await, Ok(()));
            drop(actor);
            assert_mock(mock, &hex!("00000001 01")).await;
        }
    }

    #[tokio::test]
    async fn handle_self_interested() {
        {
            let (mut actor, mock, ..) = Actor::new_mock();
            assert_matches!(actor.handle_self_interested(true).await, Ok(()));
            drop(actor);
            assert_mock(mock, &hex!("00000001 02")).await;
        }
        {
            let (mut actor, mock, ..) = Actor::new_mock();
            assert_matches!(actor.handle_self_interested(false).await, Ok(()));
            drop(actor);
            assert_mock(mock, &hex!("00000001 03")).await;
        }
    }

    #[tokio::test]
    async fn handle_incoming() {
        {
            let (mut actor, mock, ..) = Actor::new_mock();
            assert_matches!(
                actor
                    .handle_incoming(DESC3, Ok(Bytes::from_static(&hex!("aabbcc"))))
                    .await,
                Ok(()),
            );
            drop(actor);
            assert_mock(mock, &hex!("0000000c 07 00000001 00000002 aabbcc")).await;
        }
        {
            let (mut actor, mock, ..) = Actor::new_mock();
            assert_matches!(actor.handle_incoming(DESC3, Err(Reject)).await, Ok(()));
            drop(actor);
            assert_mock(mock, &hex!("0000000d 10 00000001 00000002 00000003")).await;
        }
    }

    #[tokio::test]
    async fn handle_expired() {
        let (mut actor, mock, _, _, outgoings, ..) = Actor::new_mock();
        let _response_recv = outgoings.enqueue(DESC3).unwrap().unwrap();
        actor.outgoings.assert(&[DESC3], 3, &[DESC3], &[]);

        actor.handle_expired(DESC3);
        actor.outgoings.assert(&[], 0, &[DESC3], &[]);

        drop(actor);
        assert_mock(mock, &[]).await;
    }

    #[tokio::test]
    async fn handle_new() {
        {
            let (mut actor, mock, ..) = Actor::new_mock();
            actor.conn_state.peer_choking.set(false);

            assert_matches!(actor.handle_new(DESC3).await, Ok(()));
            drop(actor);
            assert_mock(mock, &hex!("0000000d 06 00000001 00000002 00000003")).await;
        }
        {
            let (mut actor, mock, ..) = Actor::new_mock();
            actor.peer_allowed_fast.insert(1.into());

            assert_matches!(actor.handle_new(DESC3).await, Ok(()));
            drop(actor);
            assert_mock(mock, &hex!("0000000d 06 00000001 00000002 00000003")).await;
        }
        {
            let (mut actor, mock, _, _, outgoings, ..) = Actor::new_mock();
            let _response_recv = outgoings.enqueue(DESC3).unwrap().unwrap();
            actor.outgoings.assert(&[DESC3], 3, &[DESC3], &[]);

            assert_matches!(actor.handle_new(DESC3).await, Ok(()));
            actor.outgoings.assert(&[DESC3], 3, &[DESC3], &[DESC3]);

            drop(actor);
            assert_mock(mock, &hex!("00000001 02")).await;
        }
    }

    #[tokio::test]
    async fn handle_cancel() {
        let (mut actor, mock, ..) = Actor::new_mock();
        assert_matches!(actor.handle_cancel(DESC3).await, Ok(()));
        drop(actor);
        assert_mock(mock, &hex!("0000000d 08 00000001 00000002 00000003")).await;
    }

    #[tokio::test]
    async fn send_requests() {
        {
            let (mut actor, mock, ..) = Actor::new_mock();
            assert_matches!(actor.send_requests([].into()).await, Ok(()));
            drop(actor);
            assert_mock(mock, &[]).await;
        }
        {
            let (mut actor, mock, ..) = Actor::new_mock();
            assert_matches!(actor.send_requests([DESC3].into()).await, Ok(()));
            drop(actor);
            assert_mock(mock, &hex!("0000000d 06 00000001 00000002 00000003")).await;
        }
    }

    #[tokio::test]
    async fn send() {
        let (mut actor, mock, ..) = Actor::new_mock();
        assert_matches!(actor.send(Message::KeepAlive).await, Ok(()));
        drop(actor);
        assert_mock(mock, &hex!("00000000")).await;
    }
}
