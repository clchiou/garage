#![feature(entry_insert)]
#![cfg_attr(test, feature(duration_constants))]

mod bitfield;
mod progress;
mod queue;
mod schedule;
mod stat;

use std::time::Duration;

pub use crate::stat::Torrent;

g1_param::define!(max_assignments: usize = 2);
g1_param::define!(max_replicates: usize = 1);

g1_param::define!(backoff_base: Duration = Duration::from_secs(30));
