"""Demonstrate ``kernels.call_with_kernel``."""

import random
import sys
import time

from g1.asyncs import kernels
from g1.asyncs.bases import tasks
from g1.asyncs.bases import timers


async def compute(x):
    duration = random.uniform(0, 4)
    print('spend %.3f seconds computing' % duration)
    await timers.sleep(duration)
    return x * x


async def accumulate(ts):
    total = 0
    for task in ts:
        total += await task.get_result()
    return total


def main(_):
    start = time.perf_counter()
    ts = [tasks.spawn(compute(i + 1)) for i in range(10)]
    total = kernels.run(accumulate(ts))
    elapsed = time.perf_counter() - start
    print('result: %d' % total)
    print('total elapsed time: %.3f seconds' % elapsed)
    return 0


if __name__ == '__main__':
    print('before call_with_kernel: kernel=%s' % kernels.get_kernel())
    status = kernels.call_with_kernel(main, sys.argv)
    print('after call_with_kernel: kernel=%s' % kernels.get_kernel())
    sys.exit(status)
