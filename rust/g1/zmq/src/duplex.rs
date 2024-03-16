use std::future::Future;
use std::io::Error;
use std::pin::Pin;
use std::task::{Context, Poll};

use futures::sink;
use futures::stream;

use g1_base::fmt::{DebugExt, InsertPlaceholder};
use g1_base::task::PollExt;

use crate::sink::SendMultipart;
use crate::stream::RecvMultipart;
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
    impl_stream!();
}

impl sink::Sink<Multipart> for Duplex {
    impl_sink!();
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
