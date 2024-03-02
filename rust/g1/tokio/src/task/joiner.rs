use std::future::Future;
use std::iter::Fuse;

use tokio::task::{JoinError, JoinSet};

#[derive(Debug)]
pub struct Joiner<Iter, T> {
    futures: Fuse<Iter>,
    tasks: JoinSet<T>,
    concurrency: usize,
}

impl<Iter, T> Joiner<Iter, T>
where
    Iter: Iterator,
    Iter::Item: Future<Output = T> + Send + 'static,
    T: Send + 'static,
{
    pub fn new<IntoIter>(futures: IntoIter, concurrency: usize) -> Self
    where
        IntoIter: IntoIterator<Item = Iter::Item, IntoIter = Iter>,
    {
        Self {
            futures: futures.into_iter().fuse(),
            tasks: JoinSet::new(),
            concurrency,
        }
    }

    pub async fn join_next(&mut self) -> Option<Result<T, JoinError>> {
        while self.tasks.len() < self.concurrency {
            let Some(future) = self.futures.next() else {
                break;
            };
            self.tasks.spawn(future);
        }
        self.tasks.join_next().await
    }
}

#[cfg(test)]
mod tests {
    use std::cmp;
    use std::sync::{Arc, Mutex};
    use std::time::Duration;

    use tokio::time;

    use g1_base::sync::MutexExt;

    use super::*;

    #[tokio::test]
    async fn joiner() {
        let concurrent = Arc::new(Mutex::new(0));
        let max = Arc::new(Mutex::new(0));
        let futures: Vec<_> = (0..10)
            .map(|i| {
                let concurrent = concurrent.clone();
                let max = max.clone();
                async move {
                    {
                        let mut concurrent = concurrent.must_lock();
                        let mut max = max.must_lock();
                        *concurrent += 1;
                        *max = cmp::max(*max, *concurrent);
                    }
                    // TODO: Can we test this without `time::sleep`?
                    time::sleep(Duration::from_millis(100)).await;
                    *concurrent.must_lock() -= 1;
                    i
                }
            })
            .collect();

        let mut joiner = Joiner::new(futures, 3);
        let mut indexes = Vec::new();
        while let Some(i) = joiner.join_next().await {
            indexes.push(i.unwrap());
        }

        indexes.sort();
        assert_eq!(indexes, (0..10).collect::<Vec<_>>());
        assert_eq!(*concurrent.must_lock(), 0);
        assert_eq!(*max.must_lock(), 3);
    }
}
