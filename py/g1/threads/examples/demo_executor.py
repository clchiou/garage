"""Demonstrate executor."""

import random
import time

from g1.apps import bases
from g1.apps import labels
from g1.apps import parameters
from g1.apps import utils
from g1.threads import futures

import g1.threads.parts

LABELS = labels.make_labels(
    __name__,
    'executor_params',
    'executor',
)

utils.depend_parameter_for(
    LABELS.executor_params,
    parameters.define(
        __name__,
        g1.threads.parts.make_executor_params(),
    ),
)

utils.define_maker(
    g1.threads.parts.make_executor,
    {
        'params': LABELS.executor_params,
        'return': LABELS.executor,
    },
)


def square(x):
    duration = random.uniform(0, 4)
    time.sleep(duration)
    answer = x * x
    print('computing: %d^2 is %d' % (x, answer))
    return answer, duration


def main(executor: LABELS.executor):
    start = time.perf_counter()
    queue = futures.CompletionQueue()
    for i in range(10):
        queue.put(executor.submit(square, i + 1))
    queue.close()
    total = 0
    for future in queue:
        answer, duration = future.get_result()
        total += answer
        print('spend %.3f seconds computing' % duration)
    elapsed = time.perf_counter() - start
    print('result: %d' % total)
    print('total elapsed time: %.3f seconds' % elapsed)
    return 0


if __name__ == '__main__':
    bases.run(main)
