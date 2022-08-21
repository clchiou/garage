__all__ = [
    'create_engine',
    'attaching',
    'get_db_path',
    'set_sqlite_tmpdir',
    'upsert',
]

import contextlib
import functools
import logging
import os
import re
from pathlib import Path

import sqlalchemy
import sqlalchemy.pool

from g1.bases.assertions import ASSERT

LOG = logging.getLogger(__name__)

DB_URL_PATTERN = re.compile(r'sqlite(?:\+pysqlcipher)?://(?:/(.*))?')


def create_engine(
    db_url,
    *,
    check_same_thread=True,
    trace=False,
    pragmas=(),
    temporary_database_hack=False,
):
    ASSERT(
        DB_URL_PATTERN.fullmatch(db_url),
        'expect sqlite URL, not {!r}',
        db_url,
    )

    # SQLAlchemy (normally) cannot open temporary database because it
    # treats empty path string as `:memory:`.  Let us use the
    # `file:?uri=true` trick here.  (Note: Do not confuse temporary
    # database with TEMP database; they are different things.)
    if temporary_database_hack:
        db_url = 'sqlite:///file:?uri=true'
        poolclass = sqlalchemy.pool.StaticPool
    else:
        poolclass = None

    engine = sqlalchemy.create_engine(
        db_url,
        connect_args={
            'check_same_thread': check_same_thread,
        },
        poolclass=poolclass,
    )

    # It would be better to call ``add_trace`` before ``config_db``.
    if trace:
        sqlalchemy.event.listen(
            engine, 'connect', functools.partial(add_trace, db_url=db_url)
        )

    if pragmas:
        do_config_db = functools.partial(config_db, pragmas=pragmas)
    else:
        do_config_db = config_db
    sqlalchemy.event.listen(engine, 'connect', config_conn)
    sqlalchemy.event.listen(engine, 'connect', do_config_db, once=True)

    sqlalchemy.event.listen(engine, 'begin', do_begin)

    return engine


def add_trace(dbapi_conn, _, *, db_url):
    dbapi_conn.set_trace_callback(
        functools.partial(log_query, logging.getLogger(__name__), db_url)
    )


def log_query(logger, db_url, query):
    logger.debug('execute query in %r: %s', db_url, query)


#
# pysqlite have a few quirks that we have to work around.
# See: https://docs.sqlalchemy.org/en/latest/dialects/sqlite.html
#


def config_conn(dbapi_conn, _):
    dbapi_conn.isolation_level = None


def config_db(dbapi_conn, _, *, pragmas=()):
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute('PRAGMA foreign_keys = ON')
        for name, value in pragmas:
            cursor.execute('PRAGMA %s = %s' % (name, value))
    finally:
        cursor.close()


def do_begin(dbapi_conn):
    dbapi_conn.execute('BEGIN')


#
# SQLite-specific helpers.
#


def get_db_path(db_url):
    path_str = ASSERT.not_none(DB_URL_PATTERN.fullmatch(db_url)).group(1)
    if not path_str or path_str == ':memory:':
        return None
    return Path(path_str)


def set_sqlite_tmpdir(tmpdir_path):
    #
    # NOTE: Do NOT overwrite SQLITE_TMPDIR environ entry because:
    #
    # * Prior to Python 3.9, posix.putenv, which is implemented by
    #   putenv, can only keeps references to the latest values; old
    #   values are garbage collected.  (Since 3.9 [1], posix.putenv is
    #   changed to be implemented by setenv, and no longer has such
    #   problem.)
    #
    # * SQLite keeps a static reference to the SQLITE_TMPDIR value [2].
    #   Thus you must ensure that SQLITE_TMPDIR, once set and referenced
    #   by SQLite, is never overwritten (not even by a same value) so
    #   that the old value is not garbage collected; otherwise, SQLite
    #   will access a freed memory region.
    #
    # pylint: disable=line-too-long
    # [1] https://github.com/python/cpython/commit/b8d1262e8afe7b907b4a394a191739571092acdb
    # [2] https://github.com/sqlite/sqlite/blob/78043e891ab2fba7dbec1493a9d3e10ab2476745/src/os_unix.c#L5755
    # pylint: enable=line-too-long
    #
    tmpdir_path = str(tmpdir_path)
    sqlite_tmpdir = os.environ.get('SQLITE_TMPDIR')
    if sqlite_tmpdir is None:
        os.environ['SQLITE_TMPDIR'] = tmpdir_path
    else:
        ASSERT.equal(sqlite_tmpdir, tmpdir_path)
    LOG.info('SQLITE_TMPDIR = %r', os.environ['SQLITE_TMPDIR'])


_ATTACH_STMT = sqlalchemy.text('ATTACH DATABASE :db_path AS :db_name')
_DETACH_STMT = sqlalchemy.text('DETACH DATABASE :db_name')


@contextlib.contextmanager
def attaching(conn, db_name, db_path):
    """Context for attaching to a database.

    NOTE: Attached databases are not shared across connections.
    """
    conn.execute(
        _ATTACH_STMT.bindparams(db_name=db_name, db_path=str(db_path))
    )
    try:
        yield
    finally:
        conn.execute(_DETACH_STMT.bindparams(db_name=db_name))


def upsert(table):
    return table.insert().prefix_with('OR REPLACE')
