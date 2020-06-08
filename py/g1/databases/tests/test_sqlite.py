import unittest

import contextlib
import tempfile
from pathlib import Path

import sqlalchemy

from g1.databases import sqlite


class CreateEngineTest(unittest.TestCase):

    @staticmethod
    def make_metadata():
        metadata = sqlalchemy.MetaData()
        table = sqlalchemy.Table(
            'test_table',
            metadata,
            sqlalchemy.Column('test_data', sqlalchemy.Integer),
        )
        return metadata, table

    def test_db_url(self):
        with self.assertRaisesRegex(AssertionError, r'expect sqlite URL'):
            sqlite.create_engine('postgresql+psycopg2://')

    def test_create_engine(self):
        with contextlib.ExitStack() as stack:
            cm = stack.enter_context(
                self.assertLogs(sqlite.__name__, level='DEBUG')
            )
            # Use real file to force opening multiple connections.
            f = stack.enter_context(tempfile.NamedTemporaryFile())
            engine = sqlite.create_engine(
                # pylint: disable=no-member
                'sqlite:///%s' % f.name,
                trace=True,
                pragmas=(('auto_vacuum', 0), ),
            )
            metadata, table = self.make_metadata()
            conns = [stack.enter_context(engine.connect()) for _ in range(2)]
            for conn in conns:
                metadata.create_all(conn)
            # pylint: disable=no-value-for-parameter
            for i, conn in enumerate(conns):
                with conn.begin():
                    conn.execute(table.insert(), [{'test_data': 10 + i}])
            for i, conn in enumerate(conns):
                conn.execute(table.insert(), [{'test_data': i}])
        self.assertRegex(
            '\n'.join(cm.output),
            r'(?m:'
            r'^.* PRAGMA foreign_keys = ON$'
            r'\n^.* PRAGMA auto_vacuum = 0$'
            r'\n^.* PRAGMA main\.table_info\("test_table"\)$'
            r'\n^.* PRAGMA temp\.table_info\("test_table"\)$'
            r'(?s:.*CREATE TABLE.*)'
            r'\n^.* PRAGMA main\.table_info\("test_table"\)$'
            r'\n^.* BEGIN$'
            r'\n^.* INSERT INTO test_table \(test_data\) VALUES \(10\)$'
            r'\n^.* COMMIT$'
            r'\n^.* BEGIN$'
            r'\n^.* INSERT INTO test_table \(test_data\) VALUES \(11\)$'
            r'\n^.* COMMIT$'
            r'\n^.* INSERT INTO test_table \(test_data\) VALUES \(0\)$'
            r'\n^.* INSERT INTO test_table \(test_data\) VALUES \(1\)$'
            r')',
        )


class AttachingTest(unittest.TestCase):

    def test_attaching(self):

        metadata = sqlalchemy.MetaData(schema='test_db')
        table = sqlalchemy.Table(
            'test_table',
            metadata,
            sqlalchemy.Column('test_data', sqlalchemy.Integer),
        )

        with tempfile.NamedTemporaryFile() as tmpdb:

            # Ensure that ``attaching`` also accepts ``Path`` objects.
            tmpdb_path = Path(tmpdb.name)

            engine = sqlalchemy.create_engine('sqlite://')
            with engine.connect() as conn:
                with sqlite.attaching(conn, 'test_db', tmpdb_path):
                    metadata.create_all(engine)
                    # pylint: disable=no-value-for-parameter
                    conn.execute(table.insert(), {'test_data': 42})

            engine = sqlalchemy.create_engine('sqlite://')
            stmt = sqlalchemy.select([table.c.test_data])
            with engine.connect() as conn:

                with self.assertRaisesRegex(
                    sqlalchemy.exc.OperationalError,
                    r'no such table: test_db.test_table',
                ):
                    conn.execute(stmt)

                with sqlite.attaching(conn, 'test_db', tmpdb_path):
                    self.assertEqual(conn.execute(stmt).scalar(), 42)


if __name__ == '__main__':
    unittest.main()
