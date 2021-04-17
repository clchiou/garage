"""Resource pools."""

__all__ = [
    'TimeoutPool',
]

import collections
import contextlib
import dataclasses
import time


class TimeoutPool:
    """Rudimentary timeout-based resource pool.

    A pool that releases resources unused after a timeout.

    NOTE: This class is not thread-safe.
    """

    @dataclasses.dataclass(frozen=True)
    class Stats:
        num_allocations: int
        num_concurrent_resources: int
        max_concurrent_resources: int

    def __init__(
        self,
        pool_size,
        allocate,
        release,
        timeout=300,  # 5 minutes.
    ):
        # Store pairs of (resource, returned_at), sorted by returned_at
        # in ascending order.
        self._pool = collections.deque()
        self._pool_size = pool_size
        self._allocate = allocate
        self._release = release
        self._timeout = timeout
        self._num_allocations = 0
        self._num_concurrent_resources = 0
        self._max_concurrent_resources = 0

    def get_stats(self):
        return self.Stats(
            num_allocations=self._num_allocations,
            num_concurrent_resources=self._num_concurrent_resources,
            max_concurrent_resources=self._max_concurrent_resources,
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextlib.contextmanager
    def using(self):
        resource = self.get()
        try:
            yield resource
        finally:
            self.return_(resource)

    def get(self):
        """Get a resource from the pool or allocate new one when empty.

        This does not block nor raise when the pool is empty (if we want
        to implement rate limit, we could do that?).
        """
        to_allocate = not self._pool
        if to_allocate:
            resource = self._allocate()
            self._num_allocations += 1
            self._num_concurrent_resources += 1
            max_concurrent_resources = max(
                self._num_concurrent_resources, self._max_concurrent_resources
            )
        else:
            # Return the most recently released resource so that the
            # less recently released resources may grow older and then
            # released eventually.
            resource = self._pool.pop()[0]
            max_concurrent_resources = self._max_concurrent_resources
        try:
            self.cleanup()
        except Exception:
            if to_allocate:
                self._num_allocations -= 1
                self._num_concurrent_resources -= 1
            self._release(resource)
            raise
        self._max_concurrent_resources = max_concurrent_resources
        return resource

    def return_(self, resource):
        """Return the resource to the pool.

        The pool will release resources for resources that exceed the
        timeout, or when the pool is full.
        """
        now = time.monotonic()
        self._pool.append((resource, now))
        self._cleanup(now)

    def cleanup(self):
        """Release resources that exceed the timeout.

        You may call this periodically to release old resources so that
        pooled resources is not always at high water mark.  Note that
        get/return_ calls this for you; so if the program uses the pool
        frequently, you do not need to call cleanup periodically.
        """
        self._cleanup(time.monotonic())

    def _cleanup(self, now):
        deadline = now - self._timeout
        while self._pool:
            if (
                len(self._pool) > self._pool_size
                or self._pool[0][1] < deadline
            ):
                self._release_least_recently_released_resource()
            else:
                break

    def close(self):
        """Release all resources in the pool."""
        while self._pool:
            self._release_least_recently_released_resource()

    def _release_least_recently_released_resource(self):
        self._num_concurrent_resources -= 1
        self._release(self._pool.popleft()[0])
