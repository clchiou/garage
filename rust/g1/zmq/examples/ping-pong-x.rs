use std::io::Error;

use clap::Parser;
use tokio::sync::mpsc;
use zmq::{Context, DEALER, ROUTER, SNDMORE};

use g1_zmq::Socket;

#[derive(Debug, Parser)]
struct Program {
    #[arg(long)]
    ping: bool,
    #[arg(default_value = "tcp://127.0.0.1:5555")]
    endpoint: String,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        if self.ping {
            self.ping().await
        } else {
            self.pong().await
        }
    }

    async fn ping(&self) -> Result<(), Error> {
        let socket: Socket = Context::new().socket(DEALER)?.try_into()?;
        socket.connect(&self.endpoint)?;

        socket
            .send_multipart_unsafe([b"id-0".as_slice(), b"", b"ping 0"], 0)
            .await?;
        socket
            .send_multipart_unsafe([b"id-1".as_slice(), b"", b"ping 1"], 0)
            .await?;
        socket
            .send_multipart_unsafe([b"id-2".as_slice(), b"", b"ping 2"], 0)
            .await?;

        for i in 0..3 {
            let parts = socket.recv_multipart_unsafe(0).await?;
            for part in &parts {
                eprintln!("{}: -> \"{}\"", i, part.escape_ascii());
            }
        }

        Ok(())
    }

    async fn pong(&self) -> Result<(), Error> {
        let socket: Socket = Context::new().socket(ROUTER)?.try_into()?;
        socket.bind(&self.endpoint)?;
        let (parts_send, mut parts_recv) = mpsc::channel(16);
        tokio::try_join!(
            async {
                loop {
                    let mut parts = Vec::new();
                    loop {
                        let part = socket.recv_msg(0).await?;
                        eprintln!("-> \"{}\"", part.escape_ascii());
                        let more = part.get_more();
                        parts.push(part);
                        if !more {
                            break;
                        }
                    }
                    if parts.last().unwrap().as_ref() == b"exit" {
                        break;
                    }
                    parts_send.send(parts).await.unwrap();
                }
                Ok::<_, Error>(())
            },
            async {
                while let Some(parts) = parts_recv.recv().await {
                    for part in parts {
                        let empty = part.is_empty();
                        socket.send(part, SNDMORE).await?;
                        if empty {
                            break;
                        }
                    }
                    socket.send(b"pong".as_slice(), 0).await?;
                }
                Ok(())
            },
        )?;
        Ok(())
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    Program::parse().execute().await
}
