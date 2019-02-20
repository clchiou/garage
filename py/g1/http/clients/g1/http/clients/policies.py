__all__ = [
    # Rate limit.
    'unlimited',
    'TokenBucket',
    # Retry.
    'no_retry',
    'ExponentialBackoff',
]

import time

from g1.asyncs.bases import timers
from g1.bases.assertions import ASSERT


async def unlimited():
    pass


class TokenBucket:

    def __init__(self, token_rate, bucket_size):
        self._token_rate = ASSERT.greater(token_rate, 0)
        self._token_period = 1 / self._token_rate
        self._bucket_size = ASSERT.greater(bucket_size, 0)
        self._num_tokens = 0
        self._last_added = time.monotonic()

    async def __call__(self):
        self._add_tokens()
        while self._num_tokens < 1:
            await timers.sleep(self._token_period)
            self._add_tokens()
        self._num_tokens -= 1

    def _add_tokens(self):
        now = time.monotonic()
        self._num_tokens = min(
            self._num_tokens + (now - self._last_added) * self._token_rate,
            self._bucket_size,
        )
        self._last_added = now


def no_retry(_):
    return None


class ExponentialBackoff:
    """Retry ``max_retries`` times with exponential backoff.

    NOTE: This retry policy does not implement jitter of delays; if you
    are using the ``Session`` object to write to a shared resource, you
    could suffer from write conflicts.  In that case, you should use a
    retry policy with jitter.
    """

    def __init__(self, max_retries, backoff_base):
        self._max_retries = ASSERT.greater(max_retries, 0)
        self._backoff_base = ASSERT.greater(backoff_base, 0)

    def __call__(self, retry_count):
        if retry_count >= self._max_retries:
            return None
        else:
            return self._backoff_base * 2**retry_count
