use std::cmp;
use std::time::Duration;

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

        let abs_delta = if self.average > rtt {
            self.average - rtt
        } else {
            rtt - self.average
        };
        if abs_delta > self.variance {
            self.variance += (abs_delta - self.variance) / 4;
        } else {
            self.variance -= (self.variance - abs_delta) / 4;
        }

        if rtt > self.average {
            self.average += (rtt - self.average) / 8;
        } else {
            self.average -= (self.average - rtt) / 8;
        }

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
