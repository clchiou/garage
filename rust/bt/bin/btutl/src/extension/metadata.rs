use std::collections::HashSet;
use std::io::{self, Error, Write};

use bytes::{Bytes, BytesMut};
use clap::{Args, ValueEnum};
use tokio::signal;

use g1_tokio::task::Joinable;

use bt_bencode::own::bytes::Integer;
use bt_bencode::{Json, Value, Yaml, bencode};
use bt_metainfo::{Info, SanityCheck};

use crate::text;

use super::{Extension, ExtensionConn};

#[derive(Args, Debug)]
#[command(about = "Download metadata from a peer")]
pub(crate) struct DownloadMetadataCommand {
    #[command(flatten)]
    extension: Extension,

    #[arg(long, value_enum, default_value_t = Format::Debug, help = "Output format")]
    format: Format,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, ValueEnum)]
enum Format {
    Bencode,
    Debug,
    Json,
    Yaml,
}

struct DownloadMetadata {
    conn: ExtensionConn,
    id: u8,
    size: usize,
    num_pieces: usize,
}

const ID: u8 = 1;
const NAME: &[u8] = b"ut_metadata";

const SIZE_LIMIT: usize = 10 * 1024 * 1024;

const MESSAGE_TYPE: &[u8] = b"msg_type";
const PIECE: &[u8] = b"piece";
const TOTAL_SIZE: &[u8] = b"total_size";

const REQUEST: i64 = 0;
const DATA: i64 = 1;
const REJECT: i64 = 2;

// BEP 9 defines a fixed block size.
const BLOCK_SIZE: usize = 16384;

impl DownloadMetadataCommand {
    pub(crate) async fn run(&self) -> Result<(), Error> {
        let (conn, mut guard) = self.extension.spawn().await?;
        let result = tokio::select! {
            result = signal::ctrl_c() => result.and(Err(Error::other("ctrl-c received!"))),
            result = self.download(conn) => result,
            () = &mut guard => Err(Error::other("unexpected manifold exit")),
        };
        result.and(match guard.shutdown().await {
            Ok(Ok(())) => Ok(()),
            Ok(Err(error)) => Err(error.into()),
            Err(error) => Err(error.into()),
        })
    }

    async fn download(&self, conn: ExtensionConn) -> Result<(), Error> {
        let raw_info = DownloadMetadata::new(conn).run().await?;
        let info = decode_info(&raw_info)?;
        let mut writer = io::stdout();
        match self.format {
            Format::Bencode => writer.write_all(&raw_info),
            Format::Debug => text::Format::Debug.write(info, writer),
            Format::Json => text::Format::Json.write(Json(&encode_info(&info)), writer),
            Format::Yaml => text::Format::Yaml.write(Yaml(&encode_info(&info)), writer),
        }
    }
}

fn decode_info(mut buffer: &[u8]) -> Result<Info, Error> {
    // The `info` dictionary must be strict.
    let info = bt_bencode::from_slice_strict::<Info>(&mut buffer).map_err(Error::other)?;

    if !buffer.is_empty() {
        return Err(Error::other(format!(
            "trailing data: \"{}\"",
            buffer.escape_ascii(),
        )));
    }

    info.sanity_check().map_err(Error::other)?;

    Ok(info)
}

fn encode_info(info: &Info) -> Value {
    bt_bencode::to_value(info).expect("to_value")
}

impl DownloadMetadata {
    fn new(conn: ExtensionConn) -> Self {
        Self {
            conn,
            id: 0,
            size: 0,
            num_pieces: 0,
        }
    }

    async fn run(mut self) -> Result<Bytes, Error> {
        self.handshake().await?;
        self.download().await
    }

    async fn handshake(&mut self) -> Result<(), Error> {
        let handshake = bencode!({
            b"m": {
                NAME: Integer::from(ID),
            },
        });
        self.conn.send(0, encode(&handshake)).await;

        let (id, payload) = self.conn.recv().await?;
        if id != 0 {
            return Err(Error::other(format!("expect id == 0: {id}")));
        }

        let (handshake, _) = decode(payload)?;
        let (id, size) = Self::parse_handshake(&handshake).ok_or_else(|| {
            Error::other(format!(
                "peer does not support metadata download: {handshake:?}",
            ))
        })?;
        if size > SIZE_LIMIT {
            return Err(Error::other(format!("metadata size exceed limit: {size}")));
        }
        self.id = id;
        self.size = size;
        self.num_pieces = self.size.div_ceil(BLOCK_SIZE);

        Ok(())
    }

    fn parse_handshake(handshake: &Value) -> Option<(u8, usize)> {
        let handshake = handshake.as_dictionary()?;
        let id = handshake
            .get(b"m".as_slice())?
            .as_dictionary()?
            .get(NAME)?
            .as_integer()?
            .try_into()
            .ok()?;
        let size = handshake
            .get(b"metadata_size".as_slice())?
            .as_integer()?
            .try_into()
            .ok()?;
        (id != 0).then_some((id, size))
    }

    async fn download(&mut self) -> Result<Bytes, Error> {
        let mut pieces = (0..self.num_pieces).collect::<HashSet<_>>();
        for piece in 0..Integer::try_from(self.num_pieces).expect("Integer") {
            self.send(bencode!({
                MESSAGE_TYPE: REQUEST,
                PIECE: piece,
            }))
            .await;
        }

        let mut raw_info = BytesMut::zeroed(self.size);
        while !pieces.is_empty() {
            let (message, payload) = self.recv().await?;

            let (msg_type, piece) = self
                .parse_message(&message)
                .ok_or_else(|| Error::other(format!("invalid message: {message:?}")))?;

            let size = self.piece_size(piece);
            if payload.len() != size {
                return Err(Error::other(format!(
                    "expect message payload size == {}: {}",
                    size,
                    payload.len(),
                )));
            }

            match msg_type {
                REQUEST => {
                    self.send(bencode!({
                        MESSAGE_TYPE: REQUEST,
                        PIECE: Integer::try_from(piece).expect("Integer"),
                    }))
                    .await;
                }
                DATA => {
                    if pieces.remove(&piece) {
                        let start = piece * BLOCK_SIZE;
                        raw_info[start..start + payload.len()].copy_from_slice(&payload);
                    }
                }
                REJECT => return Err(Error::other(format!("peer reject out request: {piece}"))),
                _ => unreachable!(),
            }
        }

        Ok(raw_info.freeze())
    }

    fn parse_message(&self, message: &Value) -> Option<(Integer, usize)> {
        let message = message.as_dictionary()?;

        let msg_type = message.get(MESSAGE_TYPE)?.as_integer()?;

        let piece = message.get(PIECE)?.as_integer()?.try_into().ok()?;
        if piece >= self.num_pieces {
            return None;
        }

        match msg_type {
            REQUEST | REJECT => Some((msg_type, piece)),
            DATA => {
                let total_size: usize = message.get(TOTAL_SIZE)?.as_integer()?.try_into().ok()?;
                (total_size == self.size).then_some((msg_type, piece))
            }
            _ => None,
        }
    }

    fn piece_size(&self, piece: usize) -> usize {
        if piece + 1 > self.num_pieces {
            panic!();
        } else if piece + 1 == self.num_pieces {
            self.size % BLOCK_SIZE
        } else {
            BLOCK_SIZE
        }
    }

    async fn recv(&mut self) -> Result<(Value, Bytes), Error> {
        loop {
            let (id, payload) = self.conn.recv().await?;
            if id == 0 {
                // Ignore repeated handshakes.
                continue;
            }
            return if id == ID {
                decode(payload)
            } else {
                Err(Error::other(format!("unexpected extension id: {id}")))
            };
        }
    }

    async fn send(&self, request: Value) {
        self.conn.send(self.id, encode(&request)).await
    }
}

fn decode(mut buffer: Bytes) -> Result<(Value, Bytes), Error> {
    let value = bt_bencode::from_buf(&mut buffer).map_err(Error::other)?;
    Ok((value, buffer))
}

fn encode(value: &Value) -> Bytes {
    bt_bencode::to_bytes(&value).expect("encode")
}
