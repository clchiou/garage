use std::io::Error;

use clap::Parser;
use zmq::{Context, Message, REP, REQ, SNDMORE};

use g1_zmq::Socket;

#[derive(Debug, Parser)]
struct Program {
    #[arg(long)]
    ping: bool,
    #[arg(long)]
    immediate: bool,
    #[arg(long)]
    multipart: bool,
    #[arg(default_value = "tcp://127.0.0.1:5555")]
    endpoint: String,
}

impl Program {
    async fn execute(&self) -> Result<(), Error> {
        let socket = self.make_socket()?;
        eprintln!("start ping-pong");
        if self.ping {
            self.send(&socket, "ping").await?;
            self.recv(&socket).await?;
        } else {
            self.recv(&socket).await?;
            self.send(&socket, "pong").await?;
        }
        eprintln!("stop ping-pong");
        Ok(())
    }

    fn make_socket(&self) -> Result<Socket, Error> {
        let socket: Socket = Context::new()
            .socket(if self.ping { REQ } else { REP })?
            .try_into()?;
        if self.immediate {
            socket.set_immediate(true)?;
        }
        if self.ping {
            socket.connect(&self.endpoint)?;
        } else {
            socket.bind(&self.endpoint)?;
        }
        Ok(socket)
    }

    async fn send(&self, socket: &Socket, message: &str) -> Result<(), Error> {
        if self.multipart {
            let mut parts = message.bytes().peekable();
            while let Some(part) = parts.next() {
                let sndmore = if parts.peek().is_some() { SNDMORE } else { 0 };
                socket.send([part].as_slice(), sndmore).await?;
                eprintln!("<- {}", char::from(part));
            }
        } else {
            socket.send(message, 0).await?;
            eprintln!("<- {}", message);
        }
        Ok(())
    }

    async fn recv(&self, socket: &Socket) -> Result<(), Error> {
        let mut message = Message::new();
        if self.multipart {
            loop {
                socket.recv(&mut message, 0).await?;
                eprintln!("-> {}", message.as_str().unwrap());
                if !socket.get_rcvmore()? {
                    break;
                }
            }
        } else {
            socket.recv(&mut message, 0).await?;
            eprintln!("-> {}", message.as_str().unwrap());
        }
        Ok(())
    }
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    Program::parse().execute().await
}
