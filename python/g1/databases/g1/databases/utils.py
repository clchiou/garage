__all__ = [
    'executing',
]

import contextlib

import sqlalchemy.engine


@contextlib.contextmanager
def executing(connectable, statement, *args, **kwargs):
    if isinstance(connectable, sqlalchemy.engine.Connection):
        # Do NOT close Connection object that caller passes to us.
        ctx = contextlib.nullcontext(connectable)
    else:
        ctx = connectable.connect()
    with \
        ctx as conn, \
        contextlib.closing(
            conn.execute(statement, *args, **kwargs)
        ) as result \
    :
        yield result
