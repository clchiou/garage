__all__ = [
    'Cache',
    'NULL_CACHE',
]

import collections
import contextlib
import dataclasses
import hashlib
import io
import logging
import random
import tempfile
import threading
from pathlib import Path

import g1.files
from g1.bases import timers
from g1.bases.assertions import ASSERT

LOG = logging.getLogger(__name__)

# By default we keep 80% of entries post eviction.
POST_EVICTION_SIZE_RATIO = 0.8


class CacheInterface:

    @dataclasses.dataclass(frozen=True)
    class Stats:
        num_hits: int
        num_misses: int

    _SENTINEL = object()

    def get_stats(self):
        raise NotImplementedError

    def estimate_size(self):
        raise NotImplementedError

    def evict(self):
        raise NotImplementedError

    def get(self, key, default=None):
        raise NotImplementedError

    def get_file(self, key, default=None):
        raise NotImplementedError

    def set(self, key, value):
        raise NotImplementedError

    def setting_file(self, key):
        raise NotImplementedError

    def pop(self, key, default=_SENTINEL):
        raise NotImplementedError


class NullCache(CacheInterface):

    def __init__(self):
        self._num_misses = 0

    def get_stats(self):
        return self.Stats(
            num_hits=0,
            num_misses=self._num_misses,
        )

    def estimate_size(self):
        return 0

    def evict(self):
        return 0

    def get(self, key, default=None):
        del key  # Unused.
        self._num_misses += 1
        return default

    def get_file(self, key, default=None):
        del key  # Unused.
        self._num_misses += 1
        return default

    def set(self, key, value):
        pass

    @contextlib.contextmanager
    def setting_file(self, key):
        yield io.BytesIO()

    def pop(self, key, default=CacheInterface._SENTINEL):
        if default is self._SENTINEL:
            raise KeyError(key)
        return default


NULL_CACHE = NullCache()


class Cache(CacheInterface):
    """File-based LRU cache.

    Cache keys and values are bytes objects.  A cache value is stored in
    its own file, whose path the MD5 hash of its key, with the first two
    hexadecimal digits as the directory name, and the rest as the file
    name.  This two-level structure should prevent any directory grown
    too big.
    """

    @staticmethod
    def _get_relpath(key):
        hasher = hashlib.md5()
        hasher.update(key)
        digest = hasher.hexdigest()
        return Path(digest[:2]) / digest[2:]

    def __init__(
        self,
        cache_dir_path,
        capacity,
        *,
        post_eviction_size=None,
        executor=None,  # Use this to evict in the background.
    ):
        self._lock = threading.Lock()
        self._cache_dir_path = ASSERT.predicate(cache_dir_path, Path.is_dir)
        self._capacity = ASSERT.greater(capacity, 0)
        self._post_eviction_size = (
            post_eviction_size if post_eviction_size is not None else
            int(self._capacity * POST_EVICTION_SIZE_RATIO)
        )
        ASSERT(
            0 <= self._post_eviction_size <= self._capacity,
            'expect 0 <= post_eviction_size <= {}, not {}',
            self._capacity,
            self._post_eviction_size,
        )
        self._executor = executor
        # By the way, if cache cold start is an issue, we could store
        # and load this table from a file.
        self._access_log = collections.OrderedDict()
        self._num_hits = 0
        self._num_misses = 0

        # It's safe to call these methods after this point.
        self._eviction_countdown = self._estimate_eviction_countdown()
        self._maybe_evict()

    def get_stats(self):
        return self.Stats(
            num_hits=self._num_hits,
            num_misses=self._num_misses,
        )

    def _log_access(self, path):
        # Although this is a LRU cache, let's keep access counts, which
        # could be useful in understanding cache performance.
        self._access_log[path] = self._access_log.get(path, 0) + 1
        self._access_log.move_to_end(path, last=False)

    def _make_get_recency(self):
        recency_table = dict((p, r) for r, p in enumerate(self._access_log))
        least_recency = len(self._access_log)
        return lambda path: recency_table.get(path, least_recency)

    def estimate_size(self):
        dir_paths = list(_iter_dirs(self._cache_dir_path))
        if not dir_paths:
            return 0
        # Estimate the size of the cache by multiplying the two, given
        # that MD5 yields a uniform distribution.
        return len(dir_paths) * _count_files(random.choice(dir_paths))

    def _estimate_eviction_countdown(self):
        # Just a guess of how far away we are from the next eviction.
        return self._capacity - self.estimate_size()

    def _should_evict(self):
        return (
            len(self._access_log) > self._capacity
            or self._eviction_countdown < 0
        )

    def _maybe_evict(self):
        with self._lock:
            if self._should_evict():
                self._evict_require_lock_by_caller()

    def evict(self):
        with self._lock:
            return self._evict_require_lock_by_caller()

    def _evict_require_lock_by_caller(self):
        stopwatch = timers.Stopwatch()
        stopwatch.start()
        num_evicted = self._evict()
        stopwatch.stop()
        LOG.info(
            'evict %d entries in %f seconds: %s',
            num_evicted,
            stopwatch.get_duration(),
            self._cache_dir_path,
        )
        return num_evicted

    def _evict(self):
        # Estimate post-eviction size per directory, given that MD5
        # yields a uniform distribution of sizes.
        #
        # NOTE: It might "over-evict" when post_eviction_size is less
        # than 256, since in which case target_size_per_dir is likely 0.
        target_size_per_dir = int(
            self._post_eviction_size / _count_dirs(self._cache_dir_path)
        )
        get_recency = self._make_get_recency()
        num_evicted = 0
        for dir_path in _iter_dirs(self._cache_dir_path):
            num_evicted += self._evict_dir(
                dir_path, target_size_per_dir, get_recency
            )
        self._eviction_countdown = self._estimate_eviction_countdown()
        return num_evicted

    def _evict_dir(self, dir_path, target_size, get_recency):
        num_evicted = 0
        paths = list(_iter_files(dir_path))
        paths.sort(key=get_recency)
        for path in paths[target_size:]:
            path.unlink()
            count = self._access_log.pop(path, 0)
            LOG.debug('evict: %d %s', count, path)
            num_evicted += 1
        g1.files.remove_empty_dir(dir_path)
        return num_evicted

    def _get_path(self, key):
        return self._cache_dir_path / self._get_relpath(key)

    def get(self, key, default=None):
        with self._lock:
            return self._get_require_lock_by_caller(
                key, default, Path.read_bytes
            )

    def get_file(self, key, default=None):
        """Get cache entry as a pair of file object and it size.

        The caller has to close the file object.  Note that even if this
        cache entry is removed or evicted, the file will only removed by
        the file system when the file is closed.
        """
        with self._lock:
            return self._get_require_lock_by_caller(
                key,
                default,
                lambda path: (path.open('rb'), path.stat().st_size),
            )

    def _get_require_lock_by_caller(self, key, default, getter):
        path = self._get_path(key)
        if not path.exists():
            self._num_misses += 1
            return default
        value = getter(path)
        self._log_access(path)
        self._num_hits += 1
        return value

    def set(self, key, value):
        with self._lock:
            return self._set_require_lock_by_caller(
                key, lambda path: path.write_bytes(value)
            )

    @contextlib.contextmanager
    def setting_file(self, key):
        """Set a cache entry via a file-like object."""
        # We use mktemp (which is unsafe in general) because we want to
        # rename it on success, but NamedTemporaryFile's file closer
        # raises FileNotFoundError.  I think in our use case here,
        # mktemp is safe enough.
        value_tmp_path = Path(tempfile.mktemp())
        try:
            with value_tmp_path.open('wb') as value_file:
                yield value_file
            with self._lock:
                self._set_require_lock_by_caller(key, value_tmp_path.rename)
        finally:
            value_tmp_path.unlink(missing_ok=True)

    def _set_require_lock_by_caller(self, key, setter):
        path = self._get_path(key)
        if not path.exists():
            path.parent.mkdir(exist_ok=True)
            self._eviction_countdown -= 1
        setter(path)
        self._log_access(path)
        if self._should_evict():
            if self._executor:
                self._executor.submit(self._maybe_evict)
            else:
                self._evict_require_lock_by_caller()

    def pop(self, key, default=CacheInterface._SENTINEL):
        with self._lock:
            return self._pop_require_lock_by_caller(key, default)

    def _pop_require_lock_by_caller(self, key, default):
        path = self._get_path(key)
        if not path.exists():
            if default is self._SENTINEL:
                raise KeyError(key)
            return default
        value = path.read_bytes()
        path.unlink()
        g1.files.remove_empty_dir(path.parent)
        self._access_log.pop(path, None)
        self._eviction_countdown += 1
        return value


def _iter_dirs(dir_path):
    return filter(Path.is_dir, dir_path.iterdir())


def _iter_files(dir_path):
    return filter(Path.is_file, dir_path.iterdir())


def _count_dirs(dir_path):
    return sum(1 for _ in _iter_dirs(dir_path))


def _count_files(dir_path):
    return sum(1 for _ in _iter_files(dir_path))
