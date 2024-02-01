#![feature(entry_insert)]
#![feature(try_blocks)]
#![cfg_attr(test, feature(duration_constants))]

mod actor;
mod bitfield;
mod progress;
mod queue;
mod schedule;
mod stat;

use std::time::Duration;

pub use crate::actor::{DynStorage, Update};
pub use crate::stat::Torrent;

g1_param::define!(reciprocate_margin: u64 = 256 * 1024);

g1_param::define!(endgame_threshold: f64 = 0.02);
g1_param::define!(endgame_max_assignments: usize = 4);
g1_param::define!(endgame_max_replicates: usize = 4);

g1_param::define!(max_assignments: usize = 2);
g1_param::define!(max_replicates: usize = 1);

g1_param::define!(backoff_base: Duration = Duration::from_secs(30));
