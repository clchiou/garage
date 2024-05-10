use std::future::Future;
use std::io::Error;
use std::pin::Pin;
use std::task::{Context, Poll};

use futures::sink;
use futures::stream;

use g1_base::fmt::{DebugExt, InsertPlaceholder};
use g1_base::task::PollExt;

use crate::{Multipart, Socket};

/// Multipart message stream and sink that is somewhat cancel safe.
#[derive(DebugExt)]
pub struct Duplex {
    socket: Socket,
    #[debug(with = InsertPlaceholder)]
    recv_multipart: Option<RecvMultipart>,
    #[debug(with = InsertPlaceholder)]
    send_multipart: Option<SendMultipart>,
}

// TODO: I would like to declare them as `impl Future<...>`, but `feature(type_alias_impl_trait)`
// cannot handle our complex use case yet.
//
// NOTE: We omit `Send` because `Socket` is not `Sync`.
type RecvMultipart = Pin<Box<dyn Future<Output = Result<Multipart, Error>> + 'static>>;
type SendMultipart = Pin<Box<dyn Future<Output = Result<(), Error>> + 'static>>;

// While `Socket` is not `Sync`, it seems reasonable to assert that `Duplex` is indeed both `Send`
// and `Sync`, given that `Duplex` owns `Socket`, and `Stream` and `Sink` take `&mut self`.
//
// TODO: How can we prove that this is actually safe?
unsafe impl Send for Duplex {}
unsafe impl Sync for Duplex {}

impl From<Socket> for Duplex {
    fn from(socket: Socket) -> Self {
        Self::new(socket)
    }
}

impl From<Duplex> for Socket {
    fn from(duplex: Duplex) -> Self {
        duplex.into_socket()
    }
}

impl Duplex {
    pub fn new(socket: Socket) -> Self {
        Self {
            socket,
            recv_multipart: None,
            send_multipart: None,
        }
    }

    pub fn into_socket(self) -> Socket {
        self.socket
    }
}

impl stream::Stream for Duplex {
    type Item = Result<Multipart, Error>;

    fn poll_next(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        let this = self.get_mut();
        Pin::new(this.recv_multipart.get_or_insert_with(|| {
            // TODO: How can we prove that this is actually safe?
            let socket = &this.socket as *const Socket;
            Box::pin(unsafe { &*socket }.recv_multipart_unsafe(0))
        }))
        .poll(context)
        .inspect(|_| {
            this.recv_multipart = None;
        })
        .map(Some)
    }
}

impl sink::Sink<Multipart> for Duplex {
    type Error = Error;

    fn poll_ready(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Result<(), Self::Error>> {
        self.poll_flush(context)
    }

    fn start_send(self: Pin<&mut Self>, multipart: Multipart) -> Result<(), Self::Error> {
        let this = self.get_mut();
        assert!(
            this.send_multipart.is_none(),
            "expect poll_ready called beforehand",
        );
        // TODO: How can we prove that this is actually safe?
        let socket = &this.socket as *const Socket;
        this.send_multipart = Some(Box::pin(
            unsafe { &*socket }.send_multipart_unsafe(multipart, 0),
        ));
        Ok(())
    }

    fn poll_flush(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Result<(), Self::Error>> {
        let this = self.get_mut();
        let Some(send_multipart) = this.send_multipart.as_mut() else {
            return Poll::Ready(Ok(()));
        };
        Pin::new(send_multipart).poll(context).inspect(|_| {
            this.send_multipart = None;
        })
    }

    fn poll_close(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Result<(), Self::Error>> {
        self.poll_flush(context)
    }
}

#[cfg(test)]
mod tests {
    use futures::sink::SinkExt;
    use futures::stream::TryStreamExt;
    use zmq::{Context, Message, REP, REQ};

    use super::*;

    #[tokio::test]
    async fn duplex() -> Result<(), Error> {
        fn testdata() -> Multipart {
            vec![
                Message::from(b"spam".as_slice()),
                Message::from(b"egg".as_slice()),
            ]
        }

        let context = Context::new();
        let endpoint = format!("inproc://{}", std::module_path!());

        let rep = Socket::try_from(context.socket(REP)?)?;
        rep.bind(&endpoint)?;
        let mut rep = Duplex::new(rep);

        let req = Socket::try_from(context.socket(REQ)?)?;
        req.connect(&endpoint)?;
        let mut req = Duplex::new(req);

        for _ in 0..3 {
            req.send(testdata()).await?;
            assert_eq!(rep.try_next().await?, Some(testdata()));

            rep.send(testdata()).await?;
            assert_eq!(req.try_next().await?, Some(testdata()));
        }

        Ok(())
    }
}
