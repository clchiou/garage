__all__ = [
    'Unavailable',
    # Circuit breaker.
    'TristateBreakers',
    'NO_BREAK',
    # Rate limit.
    'unlimited',
    'TokenBucket',
    # Retry.
    'no_retry',
    'ExponentialBackoff',
]

import collections
import enum
import logging
import time

from g1.asyncs.bases import timers
from g1.bases import collections as g1_collections
from g1.bases.assertions import ASSERT

LOG = logging.getLogger(__name__)


class Unavailable(Exception):
    """When rate limit is exceeded or circuit breaker disconnects."""


class CircuitBreaker:

    async def __aenter__(self):
        raise NotImplementedError

    async def __aexit__(self, exc_type, exc, traceback):
        raise NotImplementedError

    def notify_success(self):
        raise NotImplementedError

    def notify_failure(self):
        raise NotImplementedError


class CircuitBreakers:

    def get(self, key: str) -> CircuitBreaker:
        raise NotImplementedError


@enum.unique
class _States(enum.Enum):
    GREEN = enum.auto()
    YELLOW = enum.auto()
    RED = enum.auto()


class _EventLog:
    """Record when events happened."""

    def __init__(self, capacity):
        self._log = collections.deque(maxlen=capacity)

    def add(self, t):
        if self._log:
            ASSERT.greater(t, self._log[-1])
        self._log.append(t)

    def count(self, t0=None):
        """Return number of events after ``t0``."""
        if t0 is None:
            return len(self._log)
        for i, t in enumerate(self._log):
            if t >= t0:
                return len(self._log) - i
        return 0

    def clear(self):
        self._log.clear()


class TristateBreaker(CircuitBreaker):
    """Tristate circuit breaker.

    It operates in three states:

    * GREEN: This is the initial state.  When in this state, it lets all
      requests pass through.  When there are ``failure_threshold``
      failures consecutively in the last ``failure_period`` seconds, it
      changes the state to RED.

    * YELLOW: When in this state, it only lets one concurrent request
      pass through, and errs out on all others.  When there are
      ``success_threshold`` successes consecutively, it changes the
      state to GREEN.  When there is a failure, it changes the state to
      RED.

    * RED: When in this state, it lets no requests pass through.  After
      ``failure_timeout`` seconds, it changes the state to YELLOW.
    """

    def __init__(
        self,
        *,
        key,
        failure_threshold,
        failure_period,
        failure_timeout,
        success_threshold,
    ):
        self._key = key
        self._failure_threshold = ASSERT.greater(failure_threshold, 0)
        self._failure_period = ASSERT.greater(failure_period, 0)
        self._failure_timeout = ASSERT.greater(failure_timeout, 0)
        self._success_threshold = ASSERT.greater(success_threshold, 0)
        self._state = _States.GREEN
        # When state is GREEN, _event_log records failures; when state
        # is YELLOW, it records successes; when state is RED, it records
        # when the state was changed to RED.
        self._event_log = _EventLog(max(failure_threshold, success_threshold))
        self._num_concurrent_requests = 0

    async def __aenter__(self):
        if self._state is _States.GREEN:
            self._num_concurrent_requests += 1
            return self

        if self._state is _States.RED:
            if (
                self._event_log.
                count(time.monotonic() - self._failure_timeout) > 0
            ):
                raise Unavailable(
                    'circuit breaker disconnected: %s' % self._key
                )
            self._change_state_yellow()

        ASSERT.is_(self._state, _States.YELLOW)
        if self._num_concurrent_requests > 0:
            raise Unavailable(
                'circuit breaker has not re-connected yet: %s' % self._key
            )

        self._num_concurrent_requests += 1
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self._num_concurrent_requests -= 1

    def notify_success(self):
        if self._state is _States.GREEN:
            self._event_log.clear()
        elif self._state is _States.YELLOW:
            self._event_log.add(time.monotonic())
            if self._event_log.count() >= self._success_threshold:
                self._change_state_green()
        else:
            ASSERT.is_(self._state, _States.RED)
            # Nothing to do here.

    def notify_failure(self):
        if self._state is _States.GREEN:
            now = time.monotonic()
            self._event_log.add(now)
            if (
                self._event_log.count(now - self._failure_period) >=
                self._failure_threshold
            ):
                self._change_state_red(now)
        elif self._state is _States.YELLOW:
            self._change_state_red(time.monotonic())
        else:
            ASSERT.is_(self._state, _States.RED)
            # Nothing to do here.

    def _change_state_green(self):
        LOG.info('TristateBreaker: change state to GREEN: %s', self._key)
        self._state = _States.GREEN
        self._event_log.clear()

    def _change_state_yellow(self):
        LOG.info('TristateBreaker: change state to YELLOW: %s', self._key)
        self._state = _States.YELLOW
        self._event_log.clear()

    def _change_state_red(self, now):
        LOG.info('TristateBreaker: change state to RED: %s', self._key)
        self._state = _States.RED
        self._event_log.clear()
        self._event_log.add(now)


class TristateBreakers(CircuitBreakers):

    def __init__(self, **breaker_kwargs):
        self._breaker_kwargs = breaker_kwargs
        self._breakers = g1_collections.LruCache(128)

    def get(self, key):
        breaker = self._breakers.get(key)
        if breaker is None:
            # pylint: disable=missing-kwoa
            breaker = self._breakers[key] = TristateBreaker(
                key=key,
                **self._breaker_kwargs,
            )
        return breaker


class NeverBreaker(CircuitBreaker):

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        pass

    def notify_success(self):
        pass

    def notify_failure(self):
        pass


class NeverBreakers(CircuitBreakers):

    def __init__(self):
        self._no_break = NeverBreaker()

    def get(self, key):
        return self._no_break


NO_BREAK = NeverBreakers()


async def unlimited():
    pass


class TokenBucket:

    def __init__(self, token_rate, bucket_size, raise_when_empty):
        self._raise_when_empty = raise_when_empty
        self._token_rate = ASSERT.greater(token_rate, 0)
        self._token_period = 1 / self._token_rate
        self._bucket_size = ASSERT.greater(bucket_size, 0)
        self._num_tokens = 0
        self._last_added = time.monotonic()

    async def __call__(self):
        self._add_tokens()
        if self._num_tokens < 1 and self._raise_when_empty:
            raise Unavailable('rate limit exceeded')
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


def no_retry(retry_count):  # pylint: disable=useless-return
    del retry_count  # Unused.
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
