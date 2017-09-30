__all__ = [
    'create_engine',
]

import sqlalchemy


def create_engine(
        db_uri, *,
        check_same_thread=False,
        echo=False,
        pragmas=()):

    engine = sqlalchemy.create_engine(
        db_uri,
        echo=echo,
        connect_args={
            'check_same_thread': check_same_thread,
        },
    )

    @sqlalchemy.event.listens_for(engine, 'connect')
    def do_connect(dbapi_connection, _):
        # Stop pysqlite issue commit automatically.
        dbapi_connection.isolation_level = None
        # Enable foreign key.
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA foreign_keys = ON')
        for name, value in pragmas:
            cursor.execute('PRAGMA %s = %s' % (name, value))
        cursor.close()

    @sqlalchemy.event.listens_for(engine, 'begin')
    def do_begin(connection):
        connection.execute('BEGIN EXCLUSIVE')

    return engine
