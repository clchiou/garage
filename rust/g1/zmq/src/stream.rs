use std::fmt;
use std::future::Future;
use std::io::Error;
use std::pin::Pin;
use std::task::{Context, Poll};

use futures::stream;

use g1_base::fmt::InsertPlaceholder;
use g1_base::task::PollExt;

use crate::{Multipart, Socket};

/// Multipart message stream that is somewhat cancel safe.
pub struct Stream<S> {
    socket: S,
    recv_multipart: Option<RecvMultipart>,
}

// TODO: I would like to declare this as `impl Future<...>`, but `feature(type_alias_impl_trait)`
// cannot handle our complex use case yet.
//
// NOTE: We omit `Send` because `Socket` is not `Sync`.
pub(crate) type RecvMultipart = Pin<Box<dyn Future<Output = Result<Multipart, Error>> + 'static>>;

impl<S> fmt::Debug for Stream<S> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Stream")
            .field("socket", &InsertPlaceholder(&self.socket))
            .field("recv_multipart", &InsertPlaceholder(&self.recv_multipart))
            .finish()
    }
}

impl<S> Stream<S> {
    pub fn new(socket: S) -> Self {
        Self {
            socket,
            recv_multipart: None,
        }
    }
}

macro_rules! impl_stream {
    () => {
        type Item = Result<Multipart, Error>;

        fn poll_next(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Option<Self::Item>> {
            let this = self.get_mut();
            Pin::new(this.recv_multipart.get_or_insert_with(|| {
                // TODO: How can we prove that this is actually safe?
                let socket = this.socket.as_ref() as *const Socket;
                Box::pin(unsafe { &*socket }.recv_multipart_unsafe(0))
            }))
            .poll(context)
            .inspect(|_| {
                this.recv_multipart = None;
            })
            .map(Some)
        }
    };
}

impl<S> stream::Stream for Stream<S>
where
    S: AsRef<Socket> + Unpin,
{
    impl_stream!();
}

#[cfg(test)]
mod tests {
    use futures::stream::TryStreamExt;
    use zmq::{Context, Message, REP, REQ};

    use super::*;

    #[tokio::test]
    async fn stream() -> Result<(), Error> {
        fn testdata() -> Multipart {
            vec![
                Message::from(b"spam".as_slice()),
                Message::from(b"egg".as_slice()),
            ]
        }

        let context = Context::new();
        let endpoint = format!("inproc://{}", std::module_path!());

        let rep: Socket = context.socket(REP)?.try_into()?;
        let mut rep_stream = Stream::new(&rep);
        rep.bind(&endpoint)?;

        let req: Socket = context.socket(REQ)?.try_into()?;
        let mut req_stream = Stream::new(&req);
        req.connect(&endpoint)?;

        for _ in 0..3 {
            req.send_multipart_unsafe(testdata(), 0).await?;
            assert_eq!(rep_stream.try_next().await?, Some(testdata()));

            rep.send_multipart_unsafe(testdata(), 0).await?;
            assert_eq!(req_stream.try_next().await?, Some(testdata()));
        }

        Ok(())
    }
}
