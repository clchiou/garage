import unittest

import re

from sqlalchemy import (
    Integer,
    String,
    and_,
)

from g1.databases import records
from g1.databases import sqlite


class RecordsSchemaTest(unittest.TestCase):

    @staticmethod
    def make_keyed_schema():
        return records.RecordsSchema(
            'test',
            [('key1', Integer), ('key2', Integer)],
            [('value1', String), ('value2', String)],
            index_column_names=[
                ('key1', 'value1'),
                ('value1', 'value2'),
            ],
        )

    @staticmethod
    def make_keyless_schema():
        return records.RecordsSchema(
            'test',
            value_column_names_and_types=[
                ('value1', String),
                ('value2', String),
            ],
            index_column_names=[
                ('value1', 'value2'),
            ],
        )

    def assert_query_regex(self, query, expect):
        self.assertRegex(re.sub(r'\s+', ' ', str(query)), expect)

    def test_keyed_schema(self):
        schema = records.RecordsSchema(
            'test',
            [('key1', Integer), ('key2', String)],
            index_column_names=[
                ('key1', 'data'),
                ('key2', 'data'),
            ],
        )
        self.assertEqual(schema.key_column_names, ('key1', 'key2'))
        self.assertEqual(schema.value_column_names, ('data', ))
        engine = sqlite.create_engine('sqlite://', trace=True)
        with self.assertLogs(sqlite.__name__, level='DEBUG') as cm:
            rs = records.Records(engine, schema)
            # Repeated creations are okay.
            for _ in range(3):
                rs.create_all()
            for _ in range(3):
                rs.create_indices()
        self.assertRegex(
            '\n'.join(cm.output),
            r'(?m:'
            r'^CREATE TABLE test \($\n'
            r'^.*key1 INTEGER NOT NULL,\s*$\n'
            r'^.*key2 VARCHAR NOT NULL,\s*$\n'
            r'^.*data BLOB NOT NULL,\s*$\n'
            r'^.*PRIMARY KEY \(key1, key2\)$\n'
            r'(?s:.*)'  # 's' makes '.' match multiple lines.
            r'^.*CREATE INDEX IF NOT EXISTS '
            r'index_test__key1__data ON test \(key1, data\)$\n'
            r'^.*CREATE INDEX IF NOT EXISTS '
            r'index_test__key2__data ON test \(key2, data\)$\n'
            r')',
        )
        self.assertTrue(schema.is_keyed())
        schema.assert_keyed()
        with self.assertRaisesRegex(AssertionError, r'expect keyless schema'):
            schema.assert_keyless()

    def test_keyless_schema(self):
        schema = records.RecordsSchema('test')
        self.assertEqual(schema.key_column_names, ())
        self.assertEqual(schema.value_column_names, ('data', ))
        engine = sqlite.create_engine('sqlite://', trace=True)
        with self.assertLogs(sqlite.__name__, level='DEBUG') as cm:
            rs = records.Records(engine, schema)
            # Repeated creations are okay.
            for _ in range(3):
                rs.create_all()
            for _ in range(3):
                rs.create_indices()
        self.assertRegex(
            '\n'.join(cm.output),
            r'(?m:'
            r'^CREATE TABLE test \($\n'
            r'^\s*data BLOB NOT NULL$\n'
            r'^\s*\)$\n'
            r')',
        )
        self.assertFalse(schema.is_keyed())
        with self.assertRaisesRegex(AssertionError, r'expect keyed schema'):
            schema.assert_keyed()
        schema.assert_keyless()

    def test_conflicting_key_name(self):
        with self.assertRaisesRegex(AssertionError, r'isdisjoint'):
            records.RecordsSchema('test', [('data', Integer)])

    def test_query_count(self):
        for schema in (self.make_keyed_schema(), self.make_keyless_schema()):
            with self.subTest(schema.is_keyed()):
                self.assert_query_regex(
                    schema.query_count(),
                    r'SELECT count\(\*\) AS \w+ FROM test',
                )
                self.assert_query_regex(
                    schema.query_count(lambda q, c: q.where(c.value1 == 1)),
                    r'SELECT count\(\*\) AS \w+ FROM test '
                    r'WHERE test.value1 = :\w+',
                )

    def test_query_contains_keys(self):
        schema = self.make_keyed_schema()
        self.assert_query_regex(
            schema.query_contains_keys((1, 2)),
            r'SELECT :\w+ AS \w+ FROM test '
            r'WHERE test.key1 = :\w+ AND test.key2 = :\w+ '
            r'LIMIT :\w+',
        )
        with self.assertRaisesRegex(AssertionError, r'expect x == 2, not 3'):
            schema.query_contains_keys((1, 2, 3))

    def test_query_keys(self):
        schema = self.make_keyed_schema()
        self.assert_query_regex(
            schema.query_keys(),
            r'SELECT test.key1, test.key2 FROM test',
        )
        self.assert_query_regex(
            schema.query_keys(lambda q, c: q.where(c.key1 == 1)),
            r'SELECT test.key1, test.key2 FROM test '
            r'WHERE test.key1 = :\w+',
        )

    def test_query_values(self):
        for schema in (self.make_keyed_schema(), self.make_keyless_schema()):
            with self.subTest(schema.is_keyed()):
                self.assert_query_regex(
                    schema.query_values(),
                    r'SELECT test.value1, test.value2 FROM test',
                )
                self.assert_query_regex(
                    schema.query_values(lambda q, c: q.where(c.value1 == 1)),
                    r'SELECT test.value1, test.value2 FROM test '
                    r'WHERE test.value1 = :\w+',
                )

    def test_query_values_by_keys(self):
        schema = self.make_keyed_schema()
        self.assert_query_regex(
            schema.query_values_by_keys((1, 2)),
            r'SELECT test.value1, test.value2 FROM test '
            r'WHERE test.key1 = :\w+ AND test.key2 = :\w+',
        )
        with self.assertRaisesRegex(AssertionError, r'expect x == 2, not 3'):
            schema.query_values_by_keys((1, 2, 3))

    def test_query_items(self):
        schema = self.make_keyed_schema()
        self.assert_query_regex(
            schema.query_items(),
            r'SELECT test.key1, test.key2, test.value1, test.value2 FROM test',
        )
        self.assert_query_regex(
            schema.query_items(
                lambda q, c: q.where(and_(c.key1 == 1, c.value1 == 2))
            ),
            r'SELECT test.key1, test.key2, test.value1, test.value2 FROM test '
            r'WHERE test.key1 = :\w+ AND test.value1 = :\w+',
        )

    def test_make_upsert_statement(self):
        schema = self.make_keyed_schema()
        self.assert_query_regex(
            schema.make_upsert_statement(),
            r'INSERT OR REPLACE INTO test \(key1, key2, value1, value2\) '
            r'VALUES \(:key1, :key2, :value1, :value2\)'
        )

    def test_make_insert_statement(self):
        schema = self.make_keyless_schema()
        self.assert_query_regex(
            schema.make_insert_statement(),
            r'INSERT INTO test \(value1, value2\) '
            r'VALUES \(:value1, :value2\)'
        )

    def test_make_delete_statement(self):
        for schema in (self.make_keyed_schema(), self.make_keyless_schema()):
            with self.subTest(schema.is_keyed()):
                self.assert_query_regex(
                    schema.make_delete_statement(),
                    r'DELETE FROM test',
                )
                self.assert_query_regex(
                    schema.
                    make_delete_statement(lambda q, c: q.where(c.value1 == 1)),
                    r'DELETE FROM test '
                    r'WHERE test.value1 = :\w+',
                )

    def test_make_record(self):
        schema = self.make_keyed_schema()
        self.assertEqual(
            schema.make_record((1, 2), (3, 4)),
            {
                'key1': 1,
                'key2': 2,
                'value1': 3,
                'value2': 4,
            },
        )
        with self.assertRaisesRegex(AssertionError, r'expect x == 2, not 3'):
            schema.make_record((1, 2, 0), (3, 4))
        with self.assertRaisesRegex(AssertionError, r'expect x == 2, not 3'):
            schema.make_record((1, 2), (3, 4, 0))


class RecordsTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.engine = sqlite.create_engine('sqlite://')

    def make_keyed_records(self):
        rs = records.Records(
            self.engine,
            RecordsSchemaTest.make_keyed_schema(),
        )
        rs.create_all()
        return rs

    def make_keyless_records(self):
        rs = records.Records(
            self.engine,
            RecordsSchemaTest.make_keyless_schema(),
        )
        rs.create_all()
        return rs

    def assert_keyed(self, actual, expect):
        self.assertEqual(bool(actual), bool(expect))
        self.assertEqual(len(actual), len(expect))
        self.assertEqual(sorted(actual.keys()), sorted(expect.keys()))
        self.assertEqual(sorted(actual.values()), sorted(expect.values()))
        self.assertEqual(sorted(actual.items()), sorted(expect.items()))
        for key_tuple, value_tuple in expect.items():
            self.assertIn(key_tuple, actual)
            self.assertEqual(actual[key_tuple], value_tuple)
            self.assertEqual(actual.get(key_tuple), value_tuple)

    def assert_keyless(self, actual, expect):
        self.assertEqual(bool(actual), bool(expect))
        self.assertEqual(len(actual), len(expect))
        self.assertEqual(sorted(actual), sorted(expect))

    def test_keyed(self):
        rs = self.make_keyed_records()
        self.assert_keyed(rs, {})

        # Repeated creations are okay.
        for _ in range(3):
            rs.create_all()
        for _ in range(3):
            rs.create_indices()

        with self.assertRaisesRegex(AssertionError, r'expect x == 2, not 3'):
            rs[1, 2, 3] = ('x', 'y')
        with self.assertRaisesRegex(AssertionError, r'expect x == 2, not 1'):
            rs[1, 2] = 'x'
        for func, args in (
            (rs.__contains__, ((1, ), )),
            (rs.get, ((1, ), )),
            (rs.update, ([((1, ), ('x', 'y'))], )),
            (rs.update, ([((1, 2), ('x', ))], )),
        ):
            with self.subTest(func):
                with self.assertRaisesRegex(
                    AssertionError, r'expect x == 2, not 1'
                ):
                    func(*args)

        self.assert_keyed(rs, {})

        with self.assertRaisesRegex(KeyError, r'\(1, 2\)'):
            rs[1, 2]  # pylint: disable=pointless-statement
        self.assertIsNone(rs.get((1, 2)))
        self.assertNotIn((1, 2), rs)
        self.assertEqual(rs.get((1, 2), 'default'), 'default')

        rs[1, 2] = ('x', 'y')
        self.assert_keyed(rs, {(1, 2): ('x', 'y')})

        rs.update({
            (3, 4): ('p', 'q'),
            (5, 6): ('a', 'b'),
        })
        self.assert_keyed(
            rs,
            {
                (1, 2): ('x', 'y'),
                (3, 4): ('p', 'q'),
                (5, 6): ('a', 'b'),
            },
        )
        self.assertEqual(rs.count(), 3)
        self.assertEqual(rs.count(lambda q, c: q.where(c.key1 <= 3)), 2)
        self.assertEqual(
            sorted(rs.search_keys(lambda q, c: q.where(c.key1 <= 3))),
            [(1, 2), (3, 4)],
        )
        self.assertEqual(
            sorted(rs.search_keys(lambda q, c: q.where(c.key1 <= 3).limit(1))),
            [(1, 2)],
        )
        self.assertEqual(
            sorted(rs.search_values(lambda q, c: q.where(c.key1 <= 3))),
            [('p', 'q'), ('x', 'y')],
        )
        self.assertEqual(
            sorted(
                rs.search_values(lambda q, c: q.where(c.key1 <= 3).limit(1))
            ),
            [('x', 'y')],
        )
        self.assertEqual(
            sorted(rs.search_items(lambda q, c: q.where(c.key1 <= 3))),
            [((1, 2), ('x', 'y')), ((3, 4), ('p', 'q'))],
        )
        self.assertEqual(
            sorted(
                rs.search_items(lambda q, c: q.where(c.key1 <= 3).limit(1))
            ),
            [((1, 2), ('x', 'y'))],
        )

        rs[1, 2] = ('u', 'v')
        self.assert_keyed(
            rs,
            {
                (1, 2): ('u', 'v'),
                (3, 4): ('p', 'q'),
                (5, 6): ('a', 'b'),
            },
        )
        rs.delete(lambda q, c: q.where(c.key1 < 4))
        self.assert_keyed(rs, {(5, 6): ('a', 'b')})

        for func, args in (
            (rs.append, (('x', 'y'), )),
            (rs.extend, ([], )),
        ):
            with self.subTest(func):
                with self.assertRaisesRegex(
                    AssertionError,
                    r'expect keyless schema',
                ):
                    func(*args)

    def test_keyless(self):
        rs = self.make_keyless_records()
        self.assert_keyless(rs, [])

        with self.assertRaisesRegex(AssertionError, r'expect x == 2, not 1'):
            rs.append(('x', ))
        with self.assertRaisesRegex(AssertionError, r'expect x == 2, not 1'):
            rs.extend([('x', )])
        self.assert_keyless(rs, [])
        self.assertEqual(sorted(rs.search_values()), [])

        rs.append(('hello', 'world'))
        self.assert_keyless(rs, [('hello', 'world')])
        self.assertEqual(rs.count(), 1)
        self.assertEqual(rs.count(lambda q, c: q.where(c.value1 == 'spam')), 0)
        self.assertEqual(
            sorted(rs.search_values(lambda q, c: q.where(c.value1 == 'spam'))),
            [],
        )

        rs.extend([('spam', 'egg')])
        self.assert_keyless(rs, [('hello', 'world'), ('spam', 'egg')])
        self.assertEqual(rs.count(lambda q, c: q.where(c.value1 == 'spam')), 1)
        self.assertEqual(
            sorted(rs.search_values(lambda q, c: q.where(c.value1 == 'spam'))),
            [('spam', 'egg')],
        )
        self.assertEqual(
            sorted(rs.search_values(lambda q, c: q.limit(1))),
            [('hello', 'world')],
        )
        rs.delete(lambda q, c: q.where(c.value1 == 'spam'))
        self.assert_keyless(rs, [('hello', 'world')])

        for method, args in (
            (rs.__contains__, (1, )),
            (rs.__getitem__, (1, )),
            (rs.__setitem__, (1, 2)),
            (rs.keys, ()),
            (rs.items, ()),
            (rs.get, (1, )),
            (rs.search_keys, ()),
            (rs.search_items, ()),
            (rs.update, ([], )),
        ):
            with self.subTest(method):
                with self.assertRaisesRegex(
                    AssertionError,
                    r'expect keyed schema',
                ):
                    # Call next in case func is a generator function.
                    next(method(*args))


if __name__ == '__main__':
    unittest.main()
