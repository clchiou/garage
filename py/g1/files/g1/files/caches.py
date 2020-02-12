__all__ = [
    'Cache',
    'NULL_CACHE',
]

import collections
import dataclasses
import hashlib
import logging
import random
from pathlib import Path

import g1.files
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

    def evict(self):
        raise NotImplementedError

    def get(self, key, default=None):
        raise NotImplementedError

    def set(self, key, value):
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

    def evict(self):
        return 0

    def get(self, key, default=None):
        del key  # Unused.
        self._num_misses += 1
        return default

    def set(self, key, value):
        pass

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
    ):
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

    def _maybe_evict(self):
        if (
            len(self._access_log) > self._capacity
            or self._eviction_countdown < 0
        ):
            self.evict()

    def evict(self):
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
        LOG.info('evict %d entries: %s', num_evicted, self._cache_dir_path)
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
        path = self._get_path(key)
        if not path.exists():
            self._num_misses += 1
            return default
        value = path.read_bytes()
        self._log_access(path)
        self._num_hits += 1
        return value

    def set(self, key, value):
        path = self._get_path(key)
        if not path.exists():
            path.parent.mkdir(exist_ok=True)
            self._eviction_countdown -= 1
        path.write_bytes(value)
        self._log_access(path)
        # Sadly this will cause some callers to wait for unexpectedly
        # long (due to unexpected eviction).  If this becomes a serious
        # issue, we should find some way to push evictions into
        # background.
        self._maybe_evict()

    def pop(self, key, default=CacheInterface._SENTINEL):
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
