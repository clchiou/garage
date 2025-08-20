#![feature(iter_intersperse)]
#![feature(iterator_try_collect)]

mod bencode;
mod metainfo;
mod storage;

use std::io::Error;

use clap::{Parser, Subcommand};

use g1_cli::tracing::TracingConfig;

use crate::bencode::BencodeCommand;
use crate::metainfo::MetainfoCommand;
use crate::storage::{ExportCommand, ImportCommand, LsCommand, RmCommand};

#[derive(Debug, Parser)]
#[command(version = g1_cli::version!())]
struct Btutl {
    #[command(flatten, next_display_order = 100)]
    tracing: TracingConfig,

    #[command(subcommand, next_display_order = 0)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Bencode(BencodeCommand),
    Metainfo(MetainfoCommand),
    Ls(LsCommand),
    Import(ImportCommand),
    Export(ExportCommand),
    Rm(RmCommand),
}

impl Btutl {
    fn execute(&self) -> Result<(), Error> {
        self.command.run()
    }
}

impl Command {
    fn run(&self) -> Result<(), Error> {
        match self {
            Self::Bencode(command) => command.run(),
            Self::Metainfo(command) => command.run(),
            Self::Ls(command) => command.run(),
            Self::Import(command) => command.run(),
            Self::Export(command) => command.run(),
            Self::Rm(command) => command.run(),
        }
    }
}

fn main() -> Result<(), Error> {
    let btutl = Btutl::parse();
    btutl.tracing.init();
    btutl.execute()
}
