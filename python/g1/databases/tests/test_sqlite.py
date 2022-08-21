import unittest

import contextlib
import os
import subprocess
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

    def test_temporary_database_hack(self):
        with tempfile.NamedTemporaryFile() as f:
            engine = sqlite.create_engine(
                'sqlite:///%s' % f.name,
                temporary_database_hack=True,
            )
            metadata, table = self.make_metadata()

            with engine.connect() as conn:
                metadata.create_all(conn)
            with engine.connect() as conn:
                self.assertEqual(
                    conn.dialect.get_table_names(conn),
                    ['test_table'],
                )

            with engine.connect() as conn:
                conn.execute(
                    table.insert(),
                    [{
                        'test_data': i
                    } for i in range(10)],
                )
            with engine.connect() as conn:
                self.assertEqual(
                    conn.execute(table.select()).all(),
                    [(i, ) for i in range(10)],
                )

            # Make sure engine does not write to the file.
            self.assertEqual(Path(f.name).read_bytes(), b'')


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


class SqliteTest(unittest.TestCase):

    def test_get_db_path(self):
        self.assertIsNone(sqlite.get_db_path('sqlite://'))
        self.assertIsNone(sqlite.get_db_path('sqlite:///'))
        self.assertIsNone(sqlite.get_db_path('sqlite:///:memory:'))
        self.assertEqual(sqlite.get_db_path('sqlite:///x'), Path('x'))
        self.assertEqual(sqlite.get_db_path('sqlite:////x'), Path('/x'))
        with self.assertRaises(AssertionError):
            sqlite.get_db_path('sqlite://:memory:')
        with self.assertRaises(AssertionError):
            sqlite.get_db_path('sqlite://x')

    def test_set_sqlite_tmpdir(self):
        original = os.environ.get('SQLITE_TMPDIR')
        try:
            # We can't test set_sqlite_tmpdir when SQLITE_TMPDIR is set.
            if original is not None:
                os.environ.pop('SQLITE_TMPDIR')

            sqlite.set_sqlite_tmpdir(Path('x/y/z'))
            proc = subprocess.run(['env'], capture_output=True, check=True)
            self.assertIn(b'SQLITE_TMPDIR=x/y/z\n', proc.stdout)

            with self.assertRaisesRegex(
                AssertionError,
                r'expect x == \'a/b/c\', not \'x/y/z\'',
            ):
                sqlite.set_sqlite_tmpdir(Path('a/b/c'))
        finally:
            if original is not None:
                os.environ['SQLITE_TMPDIR'] = original


if __name__ == '__main__':
    unittest.main()
