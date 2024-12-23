use std::time::Duration;

use tokio::time::{self, Instant};

// If you need a concurrent `TokenBucket`, you will need to implement one using a `Semaphore`.
#[derive(Debug)]
pub struct TokenBucket {
    n: f64,
    last_fill: Instant,
    rate: f64,
    size: f64,
}

impl TokenBucket {
    pub fn new(rate: f64, size: f64) -> Self {
        assert!(rate > 0.0);
        assert!(size > 0.0);
        Self {
            n: size, // Or should we start with an empty bucket?
            last_fill: Instant::now(),
            rate,
            size,
        }
    }

    pub async fn acquire(&mut self, n: f64) {
        loop {
            match self.try_acquire(n) {
                Ok(()) => break,
                Err(delay) => time::sleep(delay).await,
            }
        }
    }

    pub fn try_acquire(&mut self, n: f64) -> Result<(), Duration> {
        assert!(n <= self.size);
        self.fill();
        if self.n >= n {
            self.n -= n;
            Ok(())
        } else {
            Err(Duration::from_secs_f64((n - self.n) / self.rate))
        }
    }

    fn fill(&mut self) {
        let now = Instant::now();
        let t = now.duration_since(self.last_fill).as_secs_f64();
        self.n = (self.n + self.rate * t).min(self.size);
        self.last_fill = now;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_bucket(bucket: &TokenBucket, n: f64, last_fill: Instant) {
        assert!(
            (bucket.n - n).abs() < 1e-3,
            "assert_bucket: expect bucket.n == {}: {}",
            n,
            bucket.n
        );
        assert_eq!(bucket.last_fill, last_fill);
    }

    fn ms(millis: u64) -> Duration {
        Duration::from_millis(millis)
    }

    #[tokio::test(start_paused = true)]
    async fn acquire() {
        {
            let t0 = Instant::now();
            let mut bucket = TokenBucket::new(1.0, 3.0);
            assert_bucket(&bucket, 3.0, t0);

            bucket.acquire(1.8).await;
            assert_bucket(&bucket, 1.2, t0);

            time::advance(ms(1000)).await;
            bucket.acquire(1.8).await;
            assert_eq!(Instant::now(), t0 + ms(1000));
            assert_bucket(&bucket, 0.4, t0 + ms(1000));
        }

        {
            let t0 = Instant::now();
            let mut bucket = TokenBucket::new(1.0, 3.0);
            assert_bucket(&bucket, 3.0, t0);

            bucket.acquire(3.0).await;
            assert_bucket(&bucket, 0.0, t0);

            time::advance(ms(1000)).await;

            assert_eq!(Instant::now(), t0 + ms(1000));
            bucket.acquire(2.0).await;
            // `sleep` auto-advances the time.
            assert_eq!(Instant::now(), t0 + ms(2000));

            assert_bucket(&bucket, 0.0, t0 + ms(2000));
        }
    }

    #[tokio::test(start_paused = true)]
    async fn try_acquire() {
        let t0 = Instant::now();
        let mut bucket = TokenBucket::new(1.0, 3.0);
        assert_bucket(&bucket, 3.0, t0);

        assert_eq!(bucket.try_acquire(1.8), Ok(()));
        assert_bucket(&bucket, 1.2, t0);

        assert_eq!(bucket.try_acquire(1.3), Err(ms(100)));
        assert_eq!(bucket.try_acquire(1.4), Err(ms(200)));
        assert_eq!(bucket.try_acquire(1.8), Err(ms(600)));
        assert_bucket(&bucket, 1.2, t0);

        time::advance(ms(1000)).await;
        assert_eq!(bucket.try_acquire(1.8), Ok(()));
        assert_eq!(Instant::now(), t0 + ms(1000));
        assert_bucket(&bucket, 0.4, t0 + ms(1000));
    }

    #[tokio::test(start_paused = true)]
    async fn fill() {
        {
            let t0 = Instant::now();
            let mut bucket = TokenBucket::new(1.0, 3.0);
            assert_bucket(&bucket, 3.0, t0);

            bucket.fill();
            assert_bucket(&bucket, 3.0, t0);

            bucket.acquire(3.0).await;
            assert_bucket(&bucket, 0.0, t0);

            time::advance(ms(1000)).await;
            for _ in 0..3 {
                bucket.fill();
                assert_bucket(&bucket, 1.0, t0 + ms(1000));
            }

            time::advance(ms(1500)).await;
            for _ in 0..3 {
                bucket.fill();
                assert_bucket(&bucket, 2.5, t0 + ms(2500));
            }

            time::advance(ms(1000)).await;
            for _ in 0..3 {
                bucket.fill();
                assert_bucket(&bucket, 3.0, t0 + ms(3500));
            }
        }

        {
            let t0 = Instant::now();
            let mut bucket = TokenBucket::new(1.2, 3.0);
            assert_bucket(&bucket, 3.0, t0);

            bucket.acquire(3.0).await;
            assert_bucket(&bucket, 0.0, t0);

            time::advance(ms(1300)).await;
            for _ in 0..3 {
                bucket.fill();
                assert_bucket(&bucket, 1.56, t0 + ms(1300));
            }
        }
    }
}
