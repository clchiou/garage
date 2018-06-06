__all__ = [
    'patch_getaddrinfo',
]

import functools
import socket
import threading

# Make an alias because we will monkey-patch it.
from socket import getaddrinfo as _getaddrinfo

from garage.collections import LruCache


class CachedGetaddrinfo:
    """Cache getaddrinfo result for a certain number for queries."""

    class CacheEntry:
        def __init__(self, result):
            self.result = result
            self.num_queried = 0

    def __init__(
            self,
            expiration=1024,
            capacity=32,
            *,
            getaddrinfo_func=None):
        self._lock = threading.Lock()
        self._expiration = expiration
        self._cache = LruCache(capacity)
        self._getaddrinfo_func = getaddrinfo_func or _getaddrinfo

    @functools.wraps(_getaddrinfo)
    def __call__(self, host, port, family=0, type=0, proto=0, flags=0):
        key = (host, port, family, type, proto, flags)
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                entry.num_queried += 1
                if entry.num_queried < self._expiration:
                    return entry.result
            new_entry = self.CacheEntry(
                self._getaddrinfo_func(
                    host, port,
                    family=family,
                    type=type,
                    proto=proto,
                    flags=flags,
                ),
            )
            self._cache[key] = new_entry
            return new_entry.result


def patch_getaddrinfo():
    socket.getaddrinfo = CachedGetaddrinfo()
