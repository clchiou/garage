use std::cmp;
use std::ops::{AddAssign, SubAssign};
use std::sync::Mutex;
use std::time::Duration;

use tokio::time;

use g1_base::sync::MutexExt;

use super::{Error, MIN_PACKET_SIZE, actor::Actor, state::State};

#[derive(Debug)]
pub(super) struct Rtt {
    pub(super) average: Duration,
    pub(super) variance: Duration,
    pub(super) timeout: Duration,
}

impl Rtt {
    pub(super) fn new() -> Self {
        Self {
            average: Duration::ZERO,
            variance: Duration::ZERO,
            // Default value specified by BEP 29.
            timeout: Duration::from_millis(1000),
        }
    }

    /// Updates RTT according to the formula specified by BEP 29.
    pub(super) fn update(&mut self, rtt: Duration) {
        const MIN_TIMEOUT: Duration = Duration::from_millis(500);

        fn abs_diff(x: Duration, y: Duration) -> (Duration, fn(&mut Duration, Duration)) {
            match x.checked_sub(y) {
                Some(d) => (d, Duration::add_assign),
                None => (y - x, Duration::sub_assign),
            }
        }

        let abs_delta = self.average.abs_diff(rtt);
        // variance += (abs_delta - variance) / 4
        let (d, f) = abs_diff(abs_delta, self.variance);
        f(&mut self.variance, d / 4);

        // average += (rtt - average) / 8
        let (d, f) = abs_diff(rtt, self.average);
        f(&mut self.average, d / 8);

        self.timeout = cmp::min(
            cmp::max(self.average + self.variance * 4, MIN_TIMEOUT),
            *crate::max_rtt_timeout(),
        );
    }

    pub(super) fn expire(&mut self) {
        // The BEP 29 text is not very readable, but it seems to specify that the timeout should be
        // doubled in this case.
        self.timeout = cmp::min(self.timeout * 2, *crate::max_rtt_timeout());
    }
}

impl Actor<Mutex<State>> {
    pub(super) async fn rtt_timer(&self) -> Result<(), Error> {
        loop {
            let rtt_timeout = self.state.must_lock().send_window.rtt.timeout;
            tokio::select! {
                () = time::sleep(rtt_timeout) => self.handle_rtt_timeout().await?,
                () = self.notifiers.rtt_timer.notified() => {}
            }
        }
    }

    async fn handle_rtt_timeout(&self) -> Result<(), Error> {
        let mut packets = Vec::new();
        {
            let mut state = self.state.must_lock();
            // BEP 29 does not specify this, but it appears that libutp resends all packets upon
            // timeout.
            let mut is_packet_timeout = false;
            for seq in state.send_window.seqs().collect::<Vec<_>>() {
                if state.send_window.get(seq).unwrap().num_acks == 0 {
                    packets.push(state.make_resend_data_packet(seq)?.unwrap());
                    is_packet_timeout = true;
                }
            }
            // Here we deviate from BEP 29.  I think it makes more sense to condition the RTT
            // timeout on the in-flight queue not being empty.
            if is_packet_timeout {
                state.set_packet_size(MIN_PACKET_SIZE);
                state.send_window.set_size_limit(MIN_PACKET_SIZE);
                state.send_window.rtt.expire();
                self.notifiers.send.notify_one();

                let rtt = &state.send_window.rtt;
                tracing::debug!(
                    rtt = ?rtt.average,
                    rtt_var = ?rtt.variance,
                    rtt_timeout = ?rtt.timeout,
                    window_size_limit = state.send_window.size_limit,
                    "rtt timeout",
                );
            }
        }
        for packet in packets {
            self.outgoing_send_dont_reset_rtt_timer(packet).await?;
        }
        Ok(())
    }
}
