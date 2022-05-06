"""Handlers that modify and/or filter requests."""

__all__ = [
    'RateLimiter',
]

import logging
import math
import time

from g1.bases import collections as g1_collections
from g1.bases.assertions import ASSERT

from .. import consts
from .. import wsgi_apps

LOG = logging.getLogger(__name__)


def default_get_bucket_key(request):
    # TODO: What other headers should we look into?
    address = request.get_header('CF-Connecting-IP')
    if address is None:
        return None
    return address.strip()


class RateLimiter:
    """Rate limiter.

    When a request arrives, the rate limiter calculates its bucket key
    and retrieves (or creates) its corresponding bucket.  Then it will
    let pass or drop the request depending on the token bucket state.

    * The rate limiter can hold at most `num_buckets` token buckets, and
      will drop buckets when this number is exceeded.
    * By default, all requests needs one token, which can be overridden
      with `get_num_needed` callback.
    """

    def __init__(
        self,
        *,
        num_buckets=512,
        token_rate,
        bucket_size,
        get_bucket_key=default_get_bucket_key,
        get_num_needed=lambda _: 1,
    ):
        self._buckets = g1_collections.LruCache(num_buckets)
        self._get_bucket_key = get_bucket_key
        self._get_num_needed = get_num_needed
        self._token_rate = ASSERT.greater(token_rate, 0)
        self._bucket_size = ASSERT.greater(bucket_size, 0)

    async def __call__(self, request, response):
        del response  # Unused.
        bucket_key = self._get_bucket_key(request)
        if bucket_key is None:
            LOG.debug('cannot get bucket key from: %r', request)
            return
        bucket = self._buckets.get(bucket_key)
        if bucket is None:
            bucket = self._buckets[bucket_key] = TokenBucket(
                self._token_rate, self._bucket_size
            )
        retry_after = bucket.maybe_remove(self._get_num_needed(request))
        if retry_after is None:
            return
        raise wsgi_apps.HttpError(
            consts.Statuses.TOO_MANY_REQUESTS,
            'rate limit exceeded: bucket_key=%r retry_after=%s' %
            (bucket_key, retry_after),
            {consts.HEADER_RETRY_AFTER: str(math.ceil(retry_after))},
        )


class TokenBucket:

    def __init__(self, token_rate, bucket_size):
        self._token_rate = ASSERT.greater(token_rate, 0)
        self._bucket_size = ASSERT.greater(bucket_size, 0)
        self._num_tokens = self._bucket_size  # Bucket is full initially.
        self._last_added = time.monotonic()

    def maybe_remove(self, num_needed):
        """Remove the given number of tokens from the bucket.

        If the bucket has less tokens than the given number, this
        returns the estimated time to wait until the bucket is full.
        """
        ASSERT.greater_or_equal(num_needed, 0)
        self._add_tokens()
        if self._num_tokens >= num_needed:
            self._num_tokens -= num_needed
            return None
        return self._bucket_size / self._token_rate

    def _add_tokens(self):
        now = time.monotonic()
        self._num_tokens = min(
            self._num_tokens + (now - self._last_added) * self._token_rate,
            self._bucket_size,
        )
        self._last_added = now
