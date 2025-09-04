use std::f64::consts::LN_2;
use std::sync::Mutex;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};

use tokio::time::Instant;

use g1_base::sync::MutexExt;

//
// TODO: Can we use a weaker ordering than `SeqCst`?
//

// You cannot simply sum up `PeerStat` to get `TorrentStat`, because a peer may be transmitting
// multiple torrents simultaneously.
#[derive(Debug)]
pub struct TorrentStat {
    download: AtomicU64,
    upload: AtomicU64,
}

#[derive(Debug)]
pub struct PeerStat {
    recv_rate: Mutex<ExpMovAvg>,
    recv_sum: AtomicU64,

    send_rate: Mutex<ExpMovAvg>,
    send_sum: AtomicU64,

    /// Tracks the number of in-flight block requests (a `bt_proto::Message::Request` has been sent
    /// but a `bt_proto::Message::Piece` has not yet been received).
    // For now, we track the number of requests rather than the total size of the requested blocks,
    // since the block size is (or should be) fixed.
    inflight: AtomicUsize,
}

//
// Given an input `(x(i), t(i))`, the output `s(i)` is defined as:
// ```
// s(0) = x(0),
// s(i) = alpha(i) * x(i) + (1 - alpha(i)) * s(i - 1),
// ```
// where
// ```
// alpha(i) = 1 - decay(t(i) - t(i - 1)),
// decay(dt) = exp(-dt / tau).
// ```
//
#[derive(Debug)]
struct ExpMovAvg {
    // Data points are grouped into one-second buckets.  When time advances to the next second, `x`
    // is "merged" into `s`.  `dt = 0` represents the initial state (`i = 0`).
    x: f64,     // x(i)
    t: Instant, // t(i)
    s: f64,     // s(i - 1)
    dt: u32,    // dt = t(i) - t(i - 1)
}

// TODO: Make this configurable.
const HALF_LIFE: f64 = 60.0;

const TAU: f64 = HALF_LIFE / LN_2;

fn decay(dt: u32) -> f64 {
    (-f64::from(dt) / TAU).exp()
}

fn dt(now: Instant, earlier: Instant) -> u32 {
    now.saturating_duration_since(earlier)
        .as_secs()
        .try_into()
        .expect("u32")
}

impl TorrentStat {
    pub(crate) fn new() -> Self {
        Self {
            download: AtomicU64::new(0),
            upload: AtomicU64::new(0),
        }
    }

    pub fn download(&self) -> u64 {
        self.download.load(Ordering::SeqCst)
    }

    pub fn download_add(&self, n: u64) {
        self.download.fetch_add(n, Ordering::SeqCst);
    }

    pub fn upload(&self) -> u64 {
        self.upload.load(Ordering::SeqCst)
    }

    pub fn upload_add(&self, n: u64) {
        self.upload.fetch_add(n, Ordering::SeqCst);
    }
}

impl PeerStat {
    pub(crate) fn new() -> Self {
        Self {
            recv_rate: Mutex::new(ExpMovAvg::new()),
            recv_sum: AtomicU64::new(0),

            send_rate: Mutex::new(ExpMovAvg::new()),
            send_sum: AtomicU64::new(0),

            inflight: AtomicUsize::new(0),
        }
    }

    pub fn recv_rate(&self) -> f64 {
        self.recv_rate.must_lock().get()
    }

    pub fn recv_sum(&self) -> u64 {
        self.recv_sum.load(Ordering::SeqCst)
    }

    pub fn recv_add(&self, n: u64) {
        self.recv_rate.must_lock().add(n);
        self.recv_sum.fetch_add(n, Ordering::SeqCst);
    }

    pub fn send_rate(&self) -> f64 {
        self.send_rate.must_lock().get()
    }

    pub fn send_sum(&self) -> u64 {
        self.send_sum.load(Ordering::SeqCst)
    }

    pub fn send_add(&self, n: u64) {
        self.send_rate.must_lock().add(n);
        self.send_sum.fetch_add(n, Ordering::SeqCst);
    }

    pub fn inflight_get(&self) -> usize {
        self.inflight.load(Ordering::SeqCst)
    }

    pub fn inflight_set(&self, n: usize) {
        self.inflight.store(n, Ordering::SeqCst);
    }
}

impl ExpMovAvg {
    fn new() -> Self {
        Self {
            x: 0.0,
            t: Instant::now(),
            s: 0.0,
            dt: 0,
        }
    }

    /// Calculates a pseudo `s(i + 1)` with `x(i + 1) = 0` and `t(i + 1) = now`.
    fn get(&self) -> f64 {
        decay(dt(Instant::now(), self.t)) * self.s()
    }

    /// Calculates `s(i)`.
    fn s(&self) -> f64 {
        if self.dt == 0 {
            self.x // s(0) = x(0)
        } else {
            let decay = decay(self.dt);
            (1.0 - decay) * self.x + decay * self.s
        }
    }

    fn add(&mut self, n: u64) {
        let now = Instant::now();

        let x = f64::from(u32::try_from(n).expect("u32"));

        // Check whether `t(0)` has been initialized.
        //
        // It seems desirable that `t(i)` is independent of the time when `ExpMovAvg` was created.
        //
        // This has an issue in that it conflates "`x(0)` is zero" with "not initialized", but it
        // is probably not a big deal.
        if self.dt == 0 && self.x == 0.0 {
            self.x = x;
            self.t = now;
            return;
        }

        let dt = dt(now, self.t);
        if dt == 0 {
            // `now` has not yet advanced to the next second.
            self.x += x;
            return;
        }

        // Merge `x` into `s`.
        self.s = self.s();

        self.x = x;
        self.t = now;
        self.dt = dt;
    }
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use tokio::time;

    use super::*;

    fn assert_eq_f64(actual: f64, expect: f64) {
        assert!(
            (actual - expect).abs() < 1e-3,
            "expect = {expect}, actual = {actual}",
        );
    }

    impl ExpMovAvg {
        fn assert(&self, x: f64, s: f64, dt: u32) {
            assert_eq_f64(self.x, x);
            assert_eq_f64(self.s, s);
            assert_eq!(self.dt, dt);
        }
    }

    fn ms(millis: u64) -> Duration {
        Duration::from_millis(millis)
    }

    #[tokio::test(start_paused = true)]
    async fn get() {
        {
            let mut avg = ExpMovAvg::new();
            avg.assert(0.0, 0.0, 0);
            assert_eq_f64(avg.get(), 0.0);

            avg.x = 3.0;
            assert_eq_f64(avg.get(), 3.0);

            time::advance(ms(60000)).await; // One half-life.
            assert_eq_f64(avg.get(), 1.5);
        }

        {
            let mut avg = ExpMovAvg::new();
            avg.x = 6.0;
            avg.s = 8.0;
            avg.dt = 60; // One half-time.
            avg.assert(6.0, 8.0, 60);
            assert_eq_f64(avg.get(), 7.0);

            time::advance(ms(60000)).await; // One half-life.
            assert_eq_f64(avg.get(), 3.5);
        }
    }

    #[test]
    fn s() {
        let mut avg = ExpMovAvg::new();
        avg.assert(0.0, 0.0, 0);
        assert_eq_f64(avg.s(), 0.0);

        avg.x = 3.0;
        assert_eq_f64(avg.s(), 3.0);

        avg.dt = 60; // One half-life.
        assert_eq_f64(avg.s(), 1.5);

        avg.s = 4.0;
        assert_eq_f64(avg.s(), 3.5);

        avg.x = 0.0;
        assert_eq_f64(avg.s(), 2.0);
    }

    #[tokio::test(start_paused = true)]
    async fn add() {
        async fn test(mut avg: ExpMovAvg) {
            avg.assert(0.0, 0.0, 0);

            avg.add(1);
            avg.assert(1.0, 0.0, 0);

            time::advance(ms(999)).await;
            avg.add(2);
            avg.assert(3.0, 0.0, 0);

            time::advance(ms(1)).await;
            avg.add(4);
            avg.assert(4.0, 3.0, 1);

            time::advance(ms(500)).await;
            avg.add(8);
            avg.assert(12.0, 3.0, 1);

            time::advance(ms(499)).await;
            avg.add(16);
            avg.assert(28.0, 3.0, 1);

            time::advance(ms(1001)).await;
            avg.add(32);
            let s = (1.0 - decay(1)) * 28.0 + decay(1) * 3.0;
            avg.assert(32.0, s, 2);

            time::advance(ms(4000)).await;
            avg.add(64);
            let s = (1.0 - decay(2)) * 32.0 + decay(2) * s;
            avg.assert(64.0, s, 4);

            time::advance(ms(500)).await;
            avg.add(1);
            avg.assert(65.0, s, 4);

            time::advance(ms(500)).await;
            avg.add(2);
            let s = (1.0 - decay(4)) * 65.0 + decay(4) * s;
            avg.assert(2.0, s, 1);
        }

        test(ExpMovAvg::new()).await;

        //
        // `t(i)` is independent of the time when `ExpMovAvg` was created.
        //

        let avg = ExpMovAvg::new();
        time::advance(ms(15000)).await;
        test(avg).await;

        let avg = ExpMovAvg::new();
        time::advance(ms(123000)).await;
        test(avg).await;
    }
}
