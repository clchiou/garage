#![cfg_attr(feature = "param", feature(iterator_try_collect))]

#[cfg(feature = "param")]
pub mod param;
#[cfg(feature = "tracing")]
pub mod tracing;

#[macro_export]
macro_rules! version {
    () => {
        // Or should we enable the "cargo" clap feature and use `crate_version!` instead?
        option_env!("APP_VERSION").unwrap_or(env!("CARGO_PKG_VERSION"))
    };
}
