use std::mem::MaybeUninit;
use std::sync::Once;
use std::time::{Duration, Instant};

//
// BEP 29 is a bit ambiguous regarding how the `send_at` timestamp is produced, as well as the
// source of timestamps.  Based on the libutp code, it appears to be generated as a microsecond
// timestamp modulo 2**32.  Consequently, `send_at` is not a timestamp itself but rather a
// remainder of a timestamp that wraps around approximately every ~4300 seconds.  The source does
// not need to be a real-time clock; a monotonic clock would suffice.
//

pub(crate) type Timestamp = Duration;

pub(crate) fn now() -> Timestamp {
    static mut TIMESTAMP_BASE: MaybeUninit<Instant> = MaybeUninit::uninit();
    static TIMESTAMP_INIT: Once = Once::new();
    unsafe {
        TIMESTAMP_INIT.call_once(|| {
            TIMESTAMP_BASE.write(Instant::now());
        });
        TIMESTAMP_BASE.assume_init_ref().elapsed()
    }
}

pub(crate) fn as_micros_u32(timestamp: Timestamp) -> u32 {
    (timestamp.as_micros() % (1 << u32::BITS))
        .try_into()
        .unwrap()
}
