use std::fmt;
use std::future::Future;
use std::io::Error;
use std::pin::Pin;
use std::task::{Context, Poll};

use futures::sink;

use g1_base::fmt::InsertPlaceholder;
use g1_base::task::PollExt;

use crate::{Multipart, Socket};

/// Multipart message sink that is somewhat cancel safe.
pub struct Sink<S> {
    socket: S,
    send_multipart: Option<SendMultipart>,
}

// TODO: I would like to declare this as `impl Future<...>`, but `feature(type_alias_impl_trait)`
// cannot handle our complex use case yet.
//
// NOTE: We omit `Send` because `Socket` is not `Sync`.
pub(crate) type SendMultipart = Pin<Box<dyn Future<Output = Result<(), Error>> + 'static>>;

impl<S> fmt::Debug for Sink<S> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Sink")
            .field("socket", &InsertPlaceholder(&self.socket))
            .field("send_multipart", &InsertPlaceholder(&self.send_multipart))
            .finish()
    }
}

impl<S> Sink<S> {
    pub fn new(socket: S) -> Self {
        Self {
            socket,
            send_multipart: None,
        }
    }
}

macro_rules! impl_sink {
    () => {
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
            let socket = this.socket.as_ref() as *const Socket;
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
    };
}

impl<S> sink::Sink<Multipart> for Sink<S>
where
    S: AsRef<Socket> + Unpin,
{
    impl_sink!();
}

#[cfg(test)]
mod tests {
    use futures::sink::SinkExt;
    use zmq::{Context, Message, REP, REQ};

    use super::*;

    #[tokio::test]
    async fn sink() -> Result<(), Error> {
        fn testdata() -> Multipart {
            vec![
                Message::from(b"spam".as_slice()),
                Message::from(b"egg".as_slice()),
            ]
        }

        let context = Context::new();
        let endpoint = format!("inproc://{}", std::module_path!());

        let rep: Socket = context.socket(REP)?.try_into()?;
        let mut rep_sink = Sink::new(&rep);
        rep.bind(&endpoint)?;

        let req: Socket = context.socket(REQ)?.try_into()?;
        let mut req_sink = Sink::new(&req);
        req.connect(&endpoint)?;

        for _ in 0..3 {
            req_sink.send(testdata()).await?;
            assert_eq!(rep.recv_multipart_unsafe(0).await?, testdata());

            rep_sink.send(testdata()).await?;
            assert_eq!(req.recv_multipart_unsafe(0).await?, testdata());
        }

        Ok(())
    }
}
