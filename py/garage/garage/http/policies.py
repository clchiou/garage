"""HTTP client policy objects."""

__all__ = [
    # Rate limit policy
    'Unlimited',
    'TokenBucket',
    # Retry policy
    'NoRetry',
    'BinaryExponentialBackoff',
]

import random
import threading
import time


class Unlimited:

    def __enter__(self):
        pass

    def __exit__(self, *_):
        pass


class TokenBucket:

    def __init__(self, addition_rate, bucket_size, *, clock=time.monotonic):
        self.addition_rate = addition_rate
        self.bucket_size = bucket_size
        self._clock = clock
        self._token_available = threading.Condition()
        self._num_tokens = 0
        self._last_added = self._clock()

    def __enter__(self):
        with self._token_available:
            self._add_tokens()
            while self._num_tokens < 1:
                self._token_available.wait(1 / self.addition_rate)
                self._add_tokens()
            self._num_tokens -= 1
            self._maybe_notify()

    def __exit__(self, *_):
        with self._token_available:
            self._add_tokens()
            self._maybe_notify()

    def _add_tokens(self):
        now = self._clock()
        self._num_tokens += (now - self._last_added) * self.addition_rate
        self._num_tokens = min(self._num_tokens, self.bucket_size)
        self._last_added = now

    def _maybe_notify(self):
        num_tokens = int(self._num_tokens)
        if num_tokens > 0:
            self._token_available.notify(num_tokens)


class NoRetry:

    def __call__(self):
        yield from ()


class BinaryExponentialBackoff:

    def __init__(self, num_retries):
        self.num_retries = num_retries

    def __call__(self):
        for retry_count in range(1, self.num_retries + 1):
            yield random.randint(0, 2 ** retry_count - 1)
