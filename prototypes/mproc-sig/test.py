#!/usr/bin/env python3

import multiprocessing
import os
import signal
import sys
import threading
import time

_BEGIN = time.monotonic()
_PID = os.getpid()


def log(message, *args):
    # Print to stderr to avoid buffering.
    print(
        '%8.2f pid=%d' % (time.monotonic() - _BEGIN, _PID),
        message % args,
        file=sys.stderr,
    )


def sleep(duration):
    log('sleep start: %f', duration)
    time.sleep(duration)
    log('sleep end: %f', duration)


def main(argv):
    if len(argv) < 2:
        print(
            'usage: %s no_handler|vanilla|monkey_patch' % argv[0],
            file=sys.stderr,
        )
        return 1
    assert argv[1] in ('no_handler', 'vanilla', 'monkey_patch')

    quit_event = threading.Event()

    def handler(signum, frame):
        del frame  # Unused.
        log('receive: %s', signum)
        quit_event.set()

    if argv[1] != 'no_handler':
        log('register signal handlers for the main process')
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    if argv[1] == 'monkey_patch':
        log('monkey patch multiprocessing')
        from g1.bases import multiprocessings  # pylint: disable=import-outside-toplevel
        multiprocessings.setup_forkserver_signal_handlers()
        initializer = multiprocessings.setup_pool_worker_signal_handlers
    else:
        initializer = None

    log('test start')
    try:
        ctx = multiprocessing.get_context('forkserver')
        with ctx.Pool(initializer=initializer, processes=4) as pool:
            if argv[1] == 'no_handler':
                pool.apply(sleep, (60, ))
            else:
                pool.apply_async(
                    sleep,
                    (60, ),
                    {},
                    lambda _: log('callback is called'),
                    lambda exc: log('err_callback is called: exc=%s', exc),
                )
                log('pool.apply_async return')
                quit_event.wait()
                log('quit_event.wait return')
    except:
        log('test err')
        raise
    else:
        log('test succeed')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
