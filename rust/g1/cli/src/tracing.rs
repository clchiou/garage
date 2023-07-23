use std::io::{self, Stderr};

use clap::{ArgAction, Args};
use tracing_subscriber::{
    filter::{EnvFilter, LevelFilter},
    fmt::{self, format::FmtSpan},
    prelude::*,
};

#[derive(Args, Clone, Debug)]
pub struct TracingConfig {
    #[arg(
        long,
        short = 'v',
        action = ArgAction::Count,
        global = true,
        help = "Make tracing output more verbose",
    )]
    verbose: u8,
    #[arg(
        long,
        action = ArgAction::Count,
        global = true,
        help = "Make tracing output less verbose",
    )]
    silent: u8,

    #[arg(long, global = true, help = "Enable colored tracing output")]
    color: bool,

    #[arg(long, global = true, help = "Enable tokio console")]
    console: bool,
}

const OFF: i16 = -3;
const ERROR: i16 = -2;
const WARN: i16 = -1;
const INFO: i16 = 0;
const DEBUG: i16 = 1;
const TRACE: i16 = 2;

const LINE_NUMBER: bool = true;
const TARGET: bool = true;
const THREAD_IDS: bool = true;
const WRITER: fn() -> Stderr = io::stderr;

impl TracingConfig {
    pub fn init(&self) {
        let layer = fmt::layer()
            .compact()
            .with_ansi(self.ansi())
            .with_file(self.file())
            .with_line_number(LINE_NUMBER)
            .with_span_events(self.span_events())
            .with_target(TARGET)
            .with_thread_ids(THREAD_IDS)
            .with_writer(WRITER)
            .with_filter(self.env_filter());
        let registry = tracing_subscriber::registry().with(layer);
        if self.console {
            registry.with(console_subscriber::spawn()).init();
        } else {
            registry.init();
        }
    }

    fn level(&self) -> i16 {
        i16::from(self.verbose).saturating_sub(i16::from(self.silent))
    }

    fn ansi(&self) -> bool {
        self.level() >= DEBUG || self.color
    }

    fn file(&self) -> bool {
        self.level() >= TRACE
    }

    fn span_events(&self) -> FmtSpan {
        if self.level() >= TRACE {
            FmtSpan::NEW | FmtSpan::CLOSE
        } else {
            FmtSpan::NONE
        }
    }

    fn env_filter(&self) -> EnvFilter {
        EnvFilter::builder()
            .with_default_directive(self.level_filter().into())
            .from_env_lossy()
    }

    fn level_filter(&self) -> LevelFilter {
        match self.level() {
            level if level <= OFF => LevelFilter::OFF,
            ERROR => LevelFilter::ERROR,
            WARN => LevelFilter::WARN,
            INFO => LevelFilter::INFO,
            DEBUG => LevelFilter::DEBUG,
            level if level >= TRACE => LevelFilter::TRACE,
            // TODO: `rustc` is not smart enough to know that the patterns above are exhaustive.
            _ => std::unreachable!(),
        }
    }
}
