#![cfg_attr(test, feature(assert_matches))]

mod closure;
mod sink;
mod stream;

use std::borrow::Borrow;
use std::sync::Arc;

use tokio::net::UdpSocket;

use crate::closure::Closure;

pub use crate::sink::UdpSink;
pub use crate::stream::UdpStream;

pub fn split<Socket>(socket: Socket) -> (UdpStream<Socket>, UdpSink<Socket>)
where
    Socket: Borrow<UdpSocket> + Clone,
{
    let closure = Arc::new(Closure::new());
    (
        UdpStream::new(socket.clone(), closure.clone()),
        UdpSink::new(socket, closure),
    )
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::io::{Error, ErrorKind};
    use std::time::Duration;

    use bytes::Bytes;
    use futures::sink::SinkExt;
    use futures::stream::StreamExt;
    use tokio::time;

    use super::*;

    //
    // TODO: Can we write these tests without using `time::sleep`?
    //

    #[tokio::test]
    async fn stream() {
        let socket = Arc::new(UdpSocket::bind("127.0.0.1:0").await.unwrap());
        let endpoint = socket.local_addr().unwrap();
        let (mut stream, _) = split(socket);

        let mock_socket = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let mock_endpoint = mock_socket.local_addr().unwrap();

        let task = tokio::spawn(async move { stream.next().await });
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        assert_matches!(mock_socket.send_to(b"spam egg", endpoint).await, Ok(8));
        assert_matches!(
            task.await,
            Ok(Some(Ok((e, p)))) if e == mock_endpoint && &*p == b"spam egg",
        );
    }

    #[tokio::test]
    async fn stream_close() {
        let socket = Arc::new(UdpSocket::bind("127.0.0.1:0").await.unwrap());
        let (mut stream, mut sink) = split(socket);

        assert_eq!(stream.is_closed(), false);
        let task = tokio::spawn(async move { stream.next().await });
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        assert_matches!(sink.close().await, Ok(()));
        assert_matches!(task.await, Ok(None));
    }

    #[tokio::test]
    async fn sink() {
        let socket = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let endpoint = socket.local_addr().unwrap();
        let (_, mut sink) = split(&socket);

        let mock_socket = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let mock_endpoint = mock_socket.local_addr().unwrap();

        let task = tokio::spawn(async move {
            let mut buffer = [0u8; 16];
            let (n, e) = mock_socket.recv_from(&mut buffer).await?;
            Ok::<_, Error>((e, Bytes::copy_from_slice(&buffer[0..n])))
        });
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        let testdata = Bytes::from_static(b"spam egg");
        assert_matches!(sink.send((mock_endpoint, testdata.clone())).await, Ok(()));
        assert_matches!(task.await, Ok(Ok((e, p))) if e == endpoint && p == testdata);
    }

    #[tokio::test]
    async fn sink_close() {
        let socket = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let endpoint = socket.local_addr().unwrap();
        let (_, mut sink) = split(&socket);

        let mock_socket = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let mock_endpoint = mock_socket.local_addr().unwrap();

        let testdata = Bytes::from_static(b"spam egg");
        assert_matches!(sink.feed((mock_endpoint, testdata.clone())).await, Ok(()));

        let task = tokio::spawn(async move {
            let mut buffer = [0u8; 16];
            let (n, e) = mock_socket.recv_from(&mut buffer).await?;
            Ok::<_, Error>((e, Bytes::copy_from_slice(&buffer[0..n])))
        });
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        assert_eq!(sink.is_closed(), false);
        assert_matches!(sink.close().await, Ok(()));
        assert_eq!(sink.is_closed(), true);
        assert_matches!(task.await, Ok(Ok((e, p))) if e == endpoint && p == testdata);

        for _ in 0..3 {
            assert_matches!(sink.flush().await, Ok(()));
            assert_matches!(sink.close().await, Ok(()));
        }

        assert_matches!(
            sink.send((mock_endpoint, Bytes::new())).await,
            Err(error) if error.kind() == ErrorKind::BrokenPipe,
        );
    }
}
