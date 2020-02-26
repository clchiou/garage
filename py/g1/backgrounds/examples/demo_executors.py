"""Demonstrate background executor."""

import time

import g1.backgrounds.executors
from g1.apps import bases


def main(executor: g1.backgrounds.executors.LABELS.executor):
    for _ in range(3):
        executor.submit(time.sleep, 10)
    time.sleep(0.1)  # To make sure the jobs are started.
    return 0


if __name__ == '__main__':
    bases.run(main)
