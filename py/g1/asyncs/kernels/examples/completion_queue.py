"""Demonstrate ``CompletionQueue``."""

import random
import sys
import time

from g1.asyncs import kernels
from g1.threads import futures


async def compute(x):
    duration = random.uniform(0, 4)
    await kernels.sleep(duration)
    return x * x, duration


async def accumulate(cq):
    total = 0
    async for task in cq:
        answer, duration = await task.get_result()
        total += answer
        print('spend %.3f seconds computing' % duration)
    return total


def main(_):
    start = time.perf_counter()
    cq = kernels.CompletionQueueAdapter(futures.CompletionQueue())
    for i in range(10):
        cq.put(kernels.spawn(compute(i + 1)))
    cq.close()
    total = kernels.run(accumulate(cq))
    elapsed = time.perf_counter() - start
    print('result: %d' % total)
    print('total elapsed time: %.3f seconds' % elapsed)
    return 0


if __name__ == '__main__':
    sys.exit(kernels.call_with_kernel(main, sys.argv))
