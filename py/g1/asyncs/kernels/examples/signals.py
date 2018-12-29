"""Demonstrate signal handling."""

import os
import signal
import sys

from g1.asyncs import kernels


async def handle_signals(duration):
    print('pid: %d' % os.getpid())
    kernels.timeout_after(duration)
    queue = kernels.SignalQueue()
    try:
        signums = [signal.SIGINT, signal.SIGTERM]
        print('handle signals for %.3f seconds: %r' % (duration, signums))
        for signum in signums:
            queue.subscribe(signum)
        while True:
            print('receive signal: %r' % await queue.get())
    except kernels.Timeout:
        print('timeout')
    finally:
        queue.close()


def main(argv):
    if len(argv) < 2:
        print('usage: %s duration' % argv[0], file=sys.stderr)
        return 1
    kernels.run(handle_signals(float(argv[1])))
    return 0


if __name__ == '__main__':
    sys.exit(kernels.call_with_kernel(main, sys.argv))
