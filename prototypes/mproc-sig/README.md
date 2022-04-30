We would like to test how a Python script that uses multiprocessing will
behave when receiving a signal.

The Python script basically does these:
1. Register SIGINT and SIGTERM handler of the main process.
2. Start a forkserver and create a multiprocessing pool.
3. Apply a `sleep(60)` job to the pool asynchronously.
4. Wait for the signal handler being called.
5. Exit the pool context (regardless the job is completed or not).

We will test the Python script with and without monkey-patching the
multiprocessing module.

During test, SIGINT and SIGTERM are delivered in three ways:
* Ctrl-C (SIGINT only).
* Send the signal to the main process only.
* Send the signal to all processes via pkill.

Test results:

* Not registering signal handler.
  * Ctrl-C.
    * Observe KeyboardInterrupt in the main process (from the
      `AsyncResult.wait`) and in all child processes.
    * Press Ctrl-C twice to unblock `pool.__exit__`.

  * SIGINT, main process only.
    * Observe KeyboardInterrupt in the main process (from the
      `AsyncResult.wait`), but NOT in child processes.
    * The process exits without blocking.
  * SIGINT, all processes.
    * Same as the "main process only" scenario.

  * SIGTERM, main process only.
    * Observe a "Terminated" message.
    * The process exits without blocking.
  * SIGTERM, all processes.
    * Same as the "main process only" scenario with an extra UserWarning
      from `resource_tracker.py` on leaked semaphore objects to clean up
      at shutdown.

* Vanilla.
  * Ctrl-C.
    * Observe KeyboardInterrupt in all child processes (and thus the
      `sleep` job is cancelled).
    * `pool.__exit__` blocks forever, even when press Ctrl-C twice.

  * SIGINT, main process only.
    * Exit smoothly.
  * SIGINT, all processes.
    * Exit smoothly.

  * SIGTERM, main process only.
    * Exit smoothly.
  * SIGTERM, all processes.
    * Exit smoothly.

* Monkey-patch.
  * Ctrl-C.
    * `pool.__exit__` blocks forever, even after `sleep` is completed.

  * SIGINT, main process only.
    * `pool.__exit__` blocks forever, even after `sleep` is completed.
  * SIGINT, all processes.
    * `pool.__exit__` blocks forever, even after `sleep` is completed.

  * SIGTERM, main process only.
    * `pool.__exit__` blocks forever, even after `sleep` is completed.
  * SIGTERM, all processes.
    * `pool.__exit__` blocks forever, even after `sleep` is completed.

* If a worker process is killed, it appears that the callbacks passed to
  `apply_async` will not be called.  Since there is no (easy) way for
  the main process to know that the worker was killed (and so should
  stop waiting for the result), I guess you should **never** kill a
  worker process without also killing the main process...?
