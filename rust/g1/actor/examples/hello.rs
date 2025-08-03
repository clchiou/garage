use std::fmt;
use std::time::Duration;

use tokio::time;

struct Greeter<T>(T);

#[g1_actor::actor]
impl<T> Greeter<T>
where
    T: fmt::Display,
    T: Send + Sync + 'static,
{
    #[method()]
    async fn greet(&self, name: String) -> String {
        time::sleep(Duration::from_secs(1)).await;
        format!("{}, {}!", self.0, name)
    }
}

#[tokio::main]
async fn main() {
    let (stub, guard) = GreeterStub::spawn(Greeter("Hello"));
    println!("greet() -> {:?}", stub.greet("World".to_string()).await);
    drop(stub);
    println!("guard.await -> {:?}", guard.await);
}
