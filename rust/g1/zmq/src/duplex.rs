use std::collections::VecDeque;
use std::io::Error;
use std::pin::Pin;
use std::task::{Context, Poll};

use futures::sink;
use futures::stream;
use zmq::{Message, DONTWAIT, SNDMORE};

use crate::Socket;

pub use crate::Multipart;

/// Multipart message stream and sink that is cancel safe.
#[derive(Debug)]
pub struct Duplex {
    socket: Socket,
    send_buffer: Option<VecDeque<Message>>,
}

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
            send_buffer: None,
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
        let mut multipart = loop {
            match this.socket.socket.recv_msg(DONTWAIT) {
                Ok(message) => break vec![message],
                Err(zmq::Error::EAGAIN) => {
                    match futures::ready!(this.socket.fd.poll_read_ready(context)) {
                        Ok(mut guard) => guard.clear_ready(),
                        Err(error) => return Poll::Ready(Some(Err(error))),
                    }
                }
                Err(error) => return Poll::Ready(Some(Err(error.into()))),
            }
        };
        // [ZeroMQ](https://libzmq.readthedocs.io/en/latest/zmq_recv.html) guarantees that
        // multipart messages are atomic.
        while this.socket.socket.get_rcvmore().expect("get_rcvmore") {
            multipart.push(this.socket.socket.recv_msg(DONTWAIT).expect("recv_msg"));
        }
        Poll::Ready(Some(Ok(multipart)))
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
            this.send_buffer.is_none(),
            "expect poll_ready called beforehand",
        );
        this.send_buffer = Some(multipart.into());
        Ok(())
    }

    fn poll_flush(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Result<(), Self::Error>> {
        let this = self.get_mut();
        let Some(send_buffer) = this.send_buffer.as_mut() else {
            return Poll::Ready(Ok(()));
        };
        while let Some(mut message) = send_buffer.pop_front() {
            let sndmore = if send_buffer.is_empty() { 0 } else { SNDMORE };
            if let Err(error) = this.socket.socket.send(&mut message, sndmore | DONTWAIT) {
                send_buffer.push_front(message);
                if error == zmq::Error::EAGAIN {
                    match futures::ready!(this.socket.fd.poll_read_ready(context)) {
                        Ok(mut guard) => guard.clear_ready(),
                        Err(error) => return Poll::Ready(Err(error)),
                    }
                } else {
                    return Poll::Ready(Err(error.into()));
                }
            }
        }
        this.send_buffer = None;
        Poll::Ready(Ok(()))
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

        let mut rep = Socket::try_from(context.socket(REP)?)?;
        rep.bind(&endpoint)?;
        let mut rep = Duplex::new(rep);

        let mut req = Socket::try_from(context.socket(REQ)?)?;
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
