__all__ = [
    'create_engine',
]

import sqlalchemy


def create_engine(db_uri, check_same_thread=False, echo=False):
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

    @sqlalchemy.event.listens_for(engine, 'begin')
    def do_begin(connection):
        connection.execute('BEGIN EXCLUSIVE')

    return engine
