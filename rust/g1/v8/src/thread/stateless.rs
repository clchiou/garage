//! It does not appear to be documented, but `v8::Isolate` tends to accumulate memory over time.
//! To mitigate this issue, we regularly recreate `v8::Isolate`.

use std::num::NonZeroU64;
use std::panic;
use std::sync::mpsc::{self, Receiver, SyncSender};
use std::thread::{self, JoinHandle};

#[derive(Debug)]
pub struct Isolate {
    exec_send: SyncSender<Exec>,
    handle: JoinHandle<()>,
}

type Exec = Box<dyn FnOnce(&mut v8::Isolate) + Send>;

impl Isolate {
    pub fn spawn() -> Self {
        // Dividing "recreate" overhead by 100 should make it small enough.
        Self::with_lifespan(NonZeroU64::new(100).expect("NonZeroU64"))
    }

    pub fn with_lifespan(lifespan: NonZeroU64) -> Self {
        let (exec_send, exec_recv) = mpsc::sync_channel(32);
        let handle = thread::spawn(move || actor(exec_recv, lifespan));
        Self { exec_send, handle }
    }

    pub fn exec<F>(&self, exec: F)
    where
        F: FnOnce(&mut v8::Isolate) + Send + 'static,
    {
        self.exec_send.send(Box::new(exec)).expect("exec_send");
    }

    pub fn call<F, T>(&self, func: F) -> T
    where
        F: FnOnce(&mut v8::Isolate) -> T + Send + 'static,
        T: Send + 'static,
    {
        let (output_send, output_recv) = mpsc::sync_channel(1);
        self.exec(move |isolate| {
            let _ = output_send.send(func(isolate));
        });
        output_recv.recv().expect("output_recv")
    }

    pub fn join(self) {
        // Drop `exec_send` to trigger a graceful exit for the actor.
        let Isolate { handle, .. } = self;
        match handle.join() {
            Ok(()) => {}
            Err(error) => panic::resume_unwind(error),
        }
    }
}

fn actor(exec_recv: Receiver<Exec>, lifespan: NonZeroU64) {
    crate::assert_init();
    let mut isolate = v8::Isolate::new(Default::default());
    let mut num_execs = 0;
    while let Ok(exec) = exec_recv.recv() {
        exec(&mut isolate);
        num_execs += 1;
        if num_execs % lifespan == 0 {
            // `v8::Isolate` requires a strict order of `drop`.
            drop(isolate);
            isolate = v8::Isolate::new(Default::default());
        }
    }
}
