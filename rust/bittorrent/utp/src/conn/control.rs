//! Congestion Control

use std::cmp;
use std::collections::VecDeque;
use std::time::Duration;

use crate::timestamp::Timestamp;

//
// Implementer's notes:
// * It appears that libutp implements a congestion control algorithm that is more sophisticated
//   than the algorithm specified by BEP 29, but we do not intend to mimic libutp here.  Instead,
//   we will follow BEP 29 for now.
// * The delay values are of type `u32`, but they are stored internally as `u64` to simplify
//   wraparound handling.
//

#[derive(Debug)]
pub(super) struct DelayWindow {
    delays: VecDeque<(Timestamp, u64)>,
    min_delay: Option<u64>,
    window_size: Duration,
}

fn to_u32(x: u64) -> u32 {
    const N: u64 = 1 << u32::BITS;
    (x % N).try_into().unwrap()
}

fn measure(origin: u32, target: u32) -> i64 {
    const N: i64 = 1 << u32::BITS;
    let distance = i64::from(target) - i64::from(origin);
    let wraparound = -distance.signum() * (N - distance.abs());
    if distance.abs() <= wraparound.abs() {
        distance
    } else {
        wraparound
    }
}

impl DelayWindow {
    pub(super) fn new(window_size: Duration) -> Self {
        Self {
            delays: VecDeque::new(),
            min_delay: None,
            window_size,
        }
    }

    /// Converts the base of `delay` to the internal base or returns `None` if the conversion
    /// underflows.
    fn to_internal(&self, delay: u32) -> Option<u64> {
        match self.min_delay {
            Some(min_delay) => min_delay.checked_add_signed(measure(to_u32(min_delay), delay)),
            None => Some(delay.into()),
        }
    }

    fn shift(&mut self, offset: i64) {
        for (_, delay) in self.delays.iter_mut() {
            *delay = delay.checked_add_signed(offset).unwrap();
        }
        if let Some(min_delay) = self.min_delay.as_mut() {
            *min_delay = min_delay.checked_add_signed(offset).unwrap();
        }
    }

    pub(super) fn push(&mut self, now: Timestamp, delay: u32) {
        let delay = match self.to_internal(delay) {
            Some(delay) => delay,
            None => {
                self.shift(1 << u32::BITS);
                self.to_internal(delay).unwrap()
            }
        };
        self.delays.push_back((now, delay));
        self.min_delay = Some(cmp::min(delay, self.min_delay.unwrap_or(delay)));
        self.clear(now);
    }

    pub(super) fn clear(&mut self, now: Timestamp) {
        let mut recompute_min_delay = false;
        while let Some((t, _)) = self.delays.front().copied() {
            if t + self.window_size <= now {
                self.delays.pop_front();
                recompute_min_delay = true;
            } else {
                break;
            }
        }
        if recompute_min_delay {
            self.min_delay = self.delays.iter().map(|(_, d)| *d).min();
        }
    }

    pub(super) fn subtract_min_delay(&self, delay: u32) -> u32 {
        u32::try_from(self.to_internal(delay).unwrap() - self.min_delay.unwrap()).unwrap()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const N: u64 = 1 << u32::BITS;

    fn assert_window(window: &DelayWindow, expect: &[u64]) {
        assert_eq!(
            window.delays.iter().map(|(_, d)| *d).collect::<Vec<_>>(),
            expect,
        );
        assert_eq!(window.min_delay, expect.iter().copied().min());
    }

    #[test]
    fn test_measure() {
        fn test(p: u32, q: u32, d: i64) {
            assert_eq!(measure(p, q), d);
            assert_eq!(measure(q, p), -d);
        }

        test(0, 0, 0);
        test(1, 2, 1);
        test(2, 4, 2);
        test(3, 6, 3);
        test(1000, 2000, 1000);

        test(0, u32::MAX, -1);
        test(1, u32::MAX, -2);
        test(2, u32::MAX, -3);
        test(0, u32::MAX - 1, -2);
        test(1, u32::MAX - 2, -4);

        test(u32::MAX, u32::MAX, 0);
        test(u32::MAX - 1, u32::MAX, 1);
        test(u32::MAX - 2, u32::MAX, 2);
    }

    #[test]
    fn to_internal() {
        let mut window = DelayWindow::new(Duration::ZERO);

        assert_eq!(window.min_delay, None);
        assert_eq!(window.to_internal(0), Some(0));
        assert_eq!(window.to_internal(1), Some(1));
        assert_eq!(window.to_internal(2), Some(2));
        assert_eq!(window.to_internal(u32::MAX - 1), Some(N - 2));
        assert_eq!(window.to_internal(u32::MAX), Some(N - 1));

        for i in 0..=10 {
            window.min_delay = Some(i);
            assert_eq!(window.to_internal(0), Some(0));
            assert_eq!(window.to_internal(1), Some(1));
            assert_eq!(window.to_internal(2), Some(2));
            assert_eq!(window.to_internal(u32::MAX - 1), None);
            assert_eq!(window.to_internal(u32::MAX), None);

            for base in [N, 2 * N, 3 * N] {
                window.min_delay = Some(base + i);
                assert_eq!(window.to_internal(0), Some(base));
                assert_eq!(window.to_internal(1), Some(base + 1));
                assert_eq!(window.to_internal(2), Some(base + 2));
                assert_eq!(window.to_internal(u32::MAX - 1), Some(base - 2));
                assert_eq!(window.to_internal(u32::MAX), Some(base - 1));

                window.min_delay = Some(base - i);
                assert_eq!(window.to_internal(0), Some(base));
                assert_eq!(window.to_internal(1), Some(base + 1));
                assert_eq!(window.to_internal(2), Some(base + 2));
                assert_eq!(window.to_internal(u32::MAX - 1), Some(base - 2));
                assert_eq!(window.to_internal(u32::MAX), Some(base - 1));
            }
        }
    }

    #[test]
    fn push() {
        let mut window = DelayWindow::new(Duration::from_millis(500));
        assert_window(&window, &[]);

        window.push(Timestamp::ZERO, 10);
        assert_window(&window, &[10]);
        window.push(Timestamp::ZERO, 11);
        assert_window(&window, &[10, 11]);
        window.push(Timestamp::ZERO, 9);
        assert_window(&window, &[10, 11, 9]);

        window.push(Timestamp::ZERO + Duration::SECOND, 12);
        assert_window(&window, &[12]);

        window.clear(Timestamp::ZERO + Duration::from_secs(2));
        assert_window(&window, &[]);

        window.push(Timestamp::ZERO, 10);
        assert_window(&window, &[10]);
        window.push(Timestamp::ZERO, u32::MAX);
        assert_window(&window, &[N + 10, N - 1]);
    }

    #[test]
    fn push_empty() {
        let mut window = DelayWindow::new(Duration::ZERO);
        assert_window(&window, &[]);
        for _ in 0..3 {
            window.push(Timestamp::ZERO, 10);
            assert_window(&window, &[]);
        }
    }

    #[test]
    fn subtract_min_delay() {
        let mut window = DelayWindow::new(Duration::from_millis(500));

        window.push(Timestamp::ZERO, 10);
        assert_window(&window, &[10]);
        assert_eq!(window.subtract_min_delay(10), 0);
        assert_eq!(window.subtract_min_delay(11), 1);
        assert_eq!(window.subtract_min_delay(12), 2);

        window.push(Timestamp::ZERO, u32::MAX);
        assert_window(&window, &[N + 10, N - 1]);
        assert_eq!(window.subtract_min_delay(u32::MAX), 0);
        assert_eq!(window.subtract_min_delay(0), 1);
        assert_eq!(window.subtract_min_delay(1), 2);
    }
}
