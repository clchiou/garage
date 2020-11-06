__all__ = [
    'create_engine',
    'attaching',
    'get_db_path',
    'setting_sqlite_tmpdir',
    'upsert',
]

import contextlib
import functools
import logging
import os
import re
from pathlib import Path

import sqlalchemy

from g1.bases.assertions import ASSERT

DB_URL_PATTERN = re.compile(r'sqlite(?:\+pysqlcipher)?://(?:/(.*))?')


def create_engine(
    db_url,
    *,
    check_same_thread=True,
    trace=False,
    pragmas=(),
):
    ASSERT(
        DB_URL_PATTERN.fullmatch(db_url),
        'expect sqlite URL, not {!r}',
        db_url,
    )

    engine = sqlalchemy.create_engine(
        db_url,
        connect_args={
            'check_same_thread': check_same_thread,
        },
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


@contextlib.contextmanager
def setting_sqlite_tmpdir(tempdir_path):
    original = os.environ.get('SQLITE_TMPDIR')
    try:
        os.environ['SQLITE_TMPDIR'] = str(tempdir_path)
        yield
    finally:
        if original is None:
            os.environ.pop('SQLITE_TMPDIR')
        else:
            os.environ['SQLITE_TMPDIR'] = original


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
