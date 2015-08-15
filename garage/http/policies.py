"""HTTP client policy objects."""

__all__ = [
    # Rate limit policy
    'Unlimited',
    'MaxConcurrentRequests',
    # Retry policy
    'NoRetry',
    'BinaryExponentialBackoff',
]

import random
import threading


class Unlimited:

    def __enter__(self):
        pass

    def __exit__(self, *_):
        pass


class MaxConcurrentRequests(threading.Semaphore):
    pass


class NoRetry:

    def __call__(self):
        yield from ()


class BinaryExponentialBackoff:

    def __init__(self, num_retries):
        self.num_retries = num_retries

    def __call__(self):
        for retry_count in range(1, self.num_retries + 1):
            yield random.randint(0, 2 ** retry_count - 1)
