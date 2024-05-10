use std::io::Error;

use clap::Parser;
use futures::sink::SinkExt;
use futures::stream::TryStreamExt;
use zmq::{Context, Message, DEALER, ROUTER};

use g1_zmq::duplex::{Duplex, Multipart};
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
        let mut duplex = Duplex::from(socket);

        duplex.send(to_multipart([b"id-0", b"", b"ping 0"])).await?;
        duplex.send(to_multipart([b"id-1", b"", b"ping 1"])).await?;
        duplex.send(to_multipart([b"id-2", b"", b"ping 2"])).await?;

        for i in 0..3 {
            let Some(parts) = duplex.try_next().await? else {
                break;
            };
            for part in &parts {
                eprintln!("{}: -> \"{}\"", i, part.escape_ascii());
            }
        }

        Ok(())
    }

    async fn pong(&self) -> Result<(), Error> {
        let socket: Socket = Context::new().socket(ROUTER)?.try_into()?;
        socket.bind(&self.endpoint)?;
        let mut duplex = Duplex::from(socket);

        let mut i = 0;
        while let Some(mut parts) = duplex.try_next().await? {
            for part in &parts {
                eprintln!("{}: -> \"{}\"", i, part.escape_ascii());
            }
            i += 1;

            *parts.last_mut().unwrap() = Message::from(b"pong".as_slice());
            duplex.send(parts).await?;
        }

        Ok(())
    }
}

fn to_multipart<const N: usize>(parts: [&[u8]; N]) -> Multipart {
    parts.into_iter().map(Message::from).collect()
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    Program::parse().execute().await
}
