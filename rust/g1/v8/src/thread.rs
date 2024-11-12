//! An `Isolate` is [automatically entered][#626] when it is constructed, which makes it difficult
//! to send it to and use it in another thread.  As a workaround, we create a dedicated thread
//! actor that creates and owns an `Isolate`, and then "use" the `Isolate` via message passing.
//!
//! [#626]: https://github.com/denoland/rusty_v8/issues/626

use std::panic;
use std::sync::mpsc::{self, Receiver, SyncSender};
use std::thread::{self, JoinHandle};

#[derive(Debug)]
pub struct Isolate<S> {
    exec_send: SyncSender<Exec<S>>,
    handle: JoinHandle<()>,
}

type Exec<S> = Box<dyn FnOnce(&mut v8::Isolate, &mut S) + Send>;

impl<S> Isolate<S> {
    pub fn spawn<F>(new_state: F) -> Self
    where
        F: FnOnce(&mut v8::Isolate) -> S + Send + 'static,
        S: 'static, // TODO: Can't we remove this?
    {
        let (exec_send, exec_recv) = mpsc::sync_channel(32);
        let handle = thread::spawn(move || actor(new_state, exec_recv));
        Self { exec_send, handle }
    }

    pub fn exec<F>(&self, exec: F)
    where
        F: FnOnce(&mut v8::Isolate, &mut S) + Send + 'static,
    {
        self.exec_send.send(Box::new(exec)).expect("exec_send");
    }

    pub fn call<F, T>(&self, func: F) -> T
    where
        F: FnOnce(&mut v8::Isolate, &mut S) -> T + Send + 'static,
        T: Send + 'static,
    {
        let (output_send, output_recv) = mpsc::sync_channel(1);
        self.exec(move |isolate, state| {
            let _ = output_send.send(func(isolate, state));
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

fn actor<S, F>(new_state: F, exec_recv: Receiver<Exec<S>>)
where
    F: FnOnce(&mut v8::Isolate) -> S,
{
    crate::assert_init();
    let mut isolate = v8::Isolate::new(Default::default());
    let mut state = new_state(&mut isolate);
    while let Ok(exec) = exec_recv.recv() {
        exec(&mut isolate, &mut state);
    }
}
