"""Demonstrate ``Task.cancel``."""

import logging
import sys
import time

from g1.asyncs import kernels
from g1.asyncs.bases import tasks
from g1.asyncs.bases import timers
from g1.asyncs.kernels import errors


async def to_be_cancelled():
    try:
        await timers.sleep(4)
    except errors.TaskCancellation:
        print('catch TaskCancellation (which is expected)')
        raise


async def cancel_task(task):
    task.cancel()
    logging.info('task exception', exc_info=await task.get_exception())


@kernels.with_kernel
def main(_):
    logging.basicConfig(level=logging.INFO)
    start = time.perf_counter()
    task = tasks.spawn(to_be_cancelled)
    kernels.run(cancel_task(task))
    elapsed = time.perf_counter() - start
    print('total elapsed time: %.3f seconds' % elapsed)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
