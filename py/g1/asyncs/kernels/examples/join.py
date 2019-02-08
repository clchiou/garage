"""Demonstrate ``Task.join``."""

import random
import sys
import time

from g1.asyncs import kernels


async def compute(x):
    duration = random.uniform(0, 4)
    print('spend %.3f seconds computing' % duration)
    await kernels.sleep(duration)
    return x * x


async def accumulate(tasks):
    total = 0
    for task in tasks:
        total += await task.get_result()
    return total


def main(_):
    start = time.perf_counter()
    tasks = [kernels.spawn(compute(i + 1)) for i in range(10)]
    total = kernels.run(accumulate(tasks))
    elapsed = time.perf_counter() - start
    print('result: %d' % total)
    print('total elapsed time: %.3f seconds' % elapsed)
    return 0


if __name__ == '__main__':
    print('before main: kernel=%s' % kernels.get_kernel())
    status = main(sys.argv)
    print('after main: kernel=%s' % kernels.get_kernel())
    sys.exit(status)
