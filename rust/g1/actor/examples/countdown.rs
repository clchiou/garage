use std::time::Duration;

use tokio::time::{self, Instant, Interval};

struct Countdown {
    interval: Option<Interval>,
    count: usize,
}

#[g1_actor::actor(
    loop_(
        react = {
            let Some(_) = Self::tick(&mut self.interval) ;
            if self.countdown() {
                break;
            }
        },
    ),
)]
impl Countdown {
    #[method()]
    fn start(&mut self, count: usize) {
        self.interval = Some(time::interval(Duration::from_secs(1)));
        self.count = count;
        println!("start: {}", self.count);
    }

    async fn tick(interval: &mut Option<Interval>) -> Option<Instant> {
        Some(interval.as_mut()?.tick().await)
    }

    fn countdown(&mut self) -> bool {
        println!("count down: {}", self.count);
        self.count = self.count.saturating_sub(1);
        self.count == 0
    }
}

#[tokio::main]
async fn main() {
    let (stub, guard) = CountdownStub::spawn(Countdown {
        interval: None,
        count: 0,
    });
    println!("start() -> {:?}", stub.start(5).await);
    println!("guard.await -> {:?}", guard.await);
}
