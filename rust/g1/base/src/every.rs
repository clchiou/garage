use std::sync::atomic::{AtomicU64, Ordering};

#[macro_export]
macro_rules! every {
    ($times:expr, $action:expr $(,)?) => {{
        static EVERY: $crate::every::Every = $crate::every::Every::new($times);
        EVERY.tick(|| $action);
    }};
}

pub struct Every {
    count: AtomicU64,
    times: u64,
}

impl Every {
    pub const fn new(times: u64) -> Self {
        Self {
            count: AtomicU64::new(0),
            times,
        }
    }

    pub fn tick<F: FnOnce()>(&self, action: F) {
        if self.count.fetch_add(1, Ordering::SeqCst) % self.times == 0 {
            action();
        }
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn every() {
        let mut n = 0;
        for i in 0..10 {
            crate::every!(2, n += 1);
            assert_eq!(n, i / 2 + 1);
        }

        n = 0;
        for i in 0..10 {
            crate::every!(3, n += 1);
            assert_eq!(n, i / 3 + 1);
        }
    }
}
