use futures::sink::SinkExt;
use futures::stream::StreamExt;
use zmq::Message;

use g1_zmq::duplex::Duplex;
use g1_zmq::Socket;

fn require_send_and_sync<T: Send + Sync + 'static>(_: T) {}

fn test_socket_recv(mut socket: Socket) {
    require_send_and_sync(async move {
        let _ = socket.recv_msg(0).await;
    });
}

fn test_socket_send(mut socket: Socket, message: Message) {
    require_send_and_sync(async move {
        let _ = socket.send(message, 0).await;
    });
}

fn test_duplex_next(mut duplex: Duplex) {
    require_send_and_sync(async move {
        let _ = duplex.next().await;
    });
}

fn test_duplex_send(mut duplex: Duplex) {
    require_send_and_sync(async move {
        let _ = duplex.send(Vec::new()).await;
    });
}

fn main() {}
