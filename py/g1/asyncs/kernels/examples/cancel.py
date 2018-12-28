"""Demonstrate ``Task.cancel``."""

import sys
import time

from g1.asyncs import kernels
from g1.asyncs.kernels import errors


async def to_be_cancelled():
    try:
        await kernels.sleep(4)
    except errors.TaskCancellation:
        print('catch TaskCancellation (which is expected)')
        raise


async def cancel_task(task):
    task.cancel()


def main(_):
    start = time.perf_counter()
    task = kernels.spawn(to_be_cancelled)
    kernels.spawn(cancel_task(task))
    kernels.run()
    elapsed = time.perf_counter() - start
    print('task exception: %s' % task.get_exception_nonblocking())
    print('total elapsed time: %.3f seconds' % elapsed)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
