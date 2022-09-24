__all__ = [
    'Cache',
]

import dataclasses
import logging
import threading
import time

from sqlalchemy import (
    Column,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    func,
    select,
)

from g1.bases import timers
from g1.bases import times
from g1.bases.assertions import ASSERT

from . import sqlite

LOG = logging.getLogger(__name__)

# By default we keep 80% of entries post eviction.
POST_EVICTION_SIZE_RATIO = 0.8


def create_engine():
    return sqlite.create_engine(
        'sqlite:///file:?uri=true',
        check_same_thread=False,
        pragmas=[('synchronous', '0')],
        temporary_database_hack=True,
    )


def make_table(metadata):
    return Table(
        'cache',
        metadata,
        Column('key', String, nullable=False, primary_key=True),
        Column('value', LargeBinary, nullable=False),
        Column('used_at', Integer, nullable=False, index=True),
        Column('written_at', Integer, nullable=False, index=True),
    )


class Cache:
    """LRU cache backed by SQLite temporary database.

    To record used-at time, it writes time.monotonic_ns to a database,
    whose reference point is undefined.  This is safe as long as the
    database is temporary.  Therefore when you provide a database to a
    cache, you must make sure that database is temporary.
    """

    @dataclasses.dataclass(frozen=True)
    class Stats:
        num_hits: int
        num_misses: int

    _SENTINEL = object()

    def __init__(
        self,
        capacity,
        *,
        engine=None,  # This must be temporary.
        metadata=None,
        post_eviction_size=None,
        expire_after_write=None,
    ):
        self._lock = threading.Lock()

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
        if expire_after_write is None:
            self._expire_after_write = None
        else:
            self._expire_after_write = int(
                times.convert(
                    times.Units.SECONDS,
                    times.Units.NANOSECONDS,
                    ASSERT.greater_or_equal(expire_after_write, 0),
                )
            )

        self._engine = create_engine() if engine is None else engine
        if metadata is None:
            metadata = MetaData()
        self._table = make_table(metadata)

        self._num_hits = 0
        self._num_misses = 0

        # Or should we move this out of __init__?
        metadata.create_all(self._engine)

    def get_size(self):
        with self._lock, self._engine.begin() as conn:
            return self._get_size_require_lock_by_caller(conn)

    def _get_size_require_lock_by_caller(self, conn):
        return (
            conn.execute(select([func.count()]).select_from(self._table))\
            .scalar_one()
        )

    def get_stats(self):
        # In theory we should acquire the lock here...
        return self.Stats(
            num_hits=self._num_hits,
            num_misses=self._num_misses,
        )

    def evict(self):
        with self._lock, self._engine.begin() as conn:
            return self._evict_require_lock_by_caller(conn, None)

    def _evict_require_lock_by_caller(self, conn, keys):
        with timers.measuring_duration() as get_duration:
            num_evicted = self._do_evict_require_lock_by_caller(conn, keys)
        LOG.info(
            'evict %d entries in %f seconds',
            num_evicted,
            get_duration(),
        )
        return num_evicted

    def _do_evict_require_lock_by_caller(self, conn, keys):
        # SQLite supports non-standard LIMIT and ORDER BY clause in a
        # DELETE statement, but SQLAlchemy does not.  So here we might
        # "over evict" rows if time.monotonic_ns is not strictly
        # increasing.  But I do not think this is a big issue that we
        # should be worried about.
        used_at = conn.execute(
            select([self._table.c.used_at])\
            .order_by(self._table.c.used_at.desc())
            .limit(1)
            .offset(self._post_eviction_size)
        ).scalar()
        if used_at is None:
            return 0
        stmt = self._table.delete().where(self._table.c.used_at <= used_at)
        if keys is not None:
            stmt = stmt.where(self._table.c.key.not_in(keys))
        return conn.execute(stmt).rowcount

    def _expire_require_lock_by_caller(self, conn, now):
        with timers.measuring_duration() as get_duration:
            num_expired = self._do_expire_require_lock_by_caller(conn, now)
        LOG.info(
            'expire %d entries in %f seconds',
            num_expired,
            get_duration(),
        )
        return num_expired

    def _do_expire_require_lock_by_caller(self, conn, now):
        return conn.execute(
            self._table.delete().where(\
                self._table.c.written_at <=
                now - ASSERT.not_none(self._expire_after_write)
            )
        ).rowcount

    def get(self, key: str, default=None):
        with self._lock, self._engine.begin() as conn:
            row = conn.execute(
                select([self._table.c.value, self._table.c.written_at])\
                .where(self._table.c.key == key)
            ).one_or_none()
            if row is None:
                self._num_misses += 1
                return default
            value, written_at = row
            now = time.monotonic_ns()
            if (
                self._expire_after_write is not None
                and written_at + self._expire_after_write <= now
            ):
                self._expire_require_lock_by_caller(conn, now)
                self._num_misses += 1
                return default
            conn.execute(
                self._table.update()\
                .where(self._table.c.key == key)
                .values(used_at=now)
            )
            self._num_hits += 1
            return value

    def set(self, key: str, value: bytes):
        with self._lock, self._engine.begin() as conn:
            self._set_require_lock_by_caller(
                conn, key, value, time.monotonic_ns()
            )
            if self._get_size_require_lock_by_caller(conn) > self._capacity:
                self._evict_require_lock_by_caller(conn, [key])

    def _set_require_lock_by_caller(self, conn, key, value, now):
        conn.execute(
            sqlite.upsert(self._table)\
            .values(
                key=key,
                value=value,
                used_at=now,
                written_at=now,
            )
        )

    def pop(self, key: str, default=_SENTINEL):
        with self._lock, self._engine.begin() as conn:
            value = conn.execute(
                select([self._table.c.value])\
                .where(self._table.c.key == key)
            ).scalar()
            if value is None:
                if default is self._SENTINEL:
                    raise KeyError(key)
                return default
            conn.execute(
                self._table.delete()\
                .where(self._table.c.key == key)
            )
            return value

    def update(self, iterable=None, /, **kwargs):
        with self._lock, self._engine.begin() as conn:
            if iterable is not None:
                iterkeys = getattr(iterable, 'keys', None)
                if iterkeys is not None:
                    items = ((key, iterable[key]) for key in iterkeys())
                else:
                    items = iterable
            else:
                items = kwargs.items()
            keys = []
            now = time.monotonic_ns()
            for key, value in items:
                self._set_require_lock_by_caller(conn, key, value, now)
                keys.append(key)
            if self._get_size_require_lock_by_caller(conn) > self._capacity:
                self._evict_require_lock_by_caller(conn, keys)
