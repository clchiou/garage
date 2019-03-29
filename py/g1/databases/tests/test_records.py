import unittest

from sqlalchemy import (
    Integer,
    String,
)

from g1.databases import records
from g1.databases import sqlite


class RecordsSchemaTest(unittest.TestCase):

    def test_keyless_schema(self):
        schema = records.RecordsSchema('test', data_column_name='more_data')
        self.assertEqual(schema.key_column_names, ())
        self.assertEqual(schema.data_column_name, 'more_data')

        engine = sqlite.create_engine('sqlite://', trace=True)
        with self.assertLogs(sqlite.__name__, level='DEBUG') as cm:
            rs = records.Records(engine, schema)
            # Repeated creations are okay.
            rs.create_all()
            rs.create_all()
            rs.create_indices()
            rs.create_indices()
        self.assertRegex(
            '\n'.join(cm.output),
            r'(?m:'
            r'^.*CREATE TABLE test \($'
            r'\n^.*more_data BLOB NOT NULL\s*$'
            r'\n^.*\)\s*$'
            r')',
        )

    def test_keyed_schema(self):

        with self.assertRaises(AssertionError):
            records.RecordsSchema('test', (('data', Integer), ))

        schema = records.RecordsSchema(
            'test',
            (('key1', Integer), ('key2', String)),
        )
        self.assertEqual(schema.key_column_names, ('key1', 'key2'))
        self.assertEqual(schema.data_column_name, 'data')

        engine = sqlite.create_engine('sqlite://', trace=True)
        with self.assertLogs(sqlite.__name__, level='DEBUG') as cm:
            rs = records.Records(engine, schema)
            # Repeated creations are okay.
            rs.create_all()
            rs.create_all()
            rs.create_indices()
            rs.create_indices()
        self.assertRegex(
            '\n'.join(cm.output),
            r'(?m:'
            r'^.*CREATE TABLE test \($'
            r'\n^.*key1 INTEGER NOT NULL,\s*$'
            r'\n^.*key2 VARCHAR NOT NULL,\s*$'
            r'\n^.*data BLOB NOT NULL,\s*$'
            r'\n^.*CONSTRAINT unique_test__key1__key2 '
            r'UNIQUE \(key1, key2\)\s*$'
            r'\n^.*\)\s*$'
            r'(?s:.*)'  # 's' makes '.' match multiple lines.
            r'\n^.*CREATE INDEX IF NOT EXISTS '
            r'index_test__key1__key2 ON test \(key1, key2\)\s*$'
            r'\n^.*CREATE INDEX IF NOT EXISTS '
            r'index_test__key1__key2 ON test \(key1, key2\)\s*$'
            r')',
        )


class RecordsTest(unittest.TestCase):

    def assert_records(self, rs, keys_list, records_list):
        self.assertEqual(bool(rs), bool(records_list))
        self.assertEqual(len(rs), len(records_list))
        self.assertEqual(list(rs.records()), records_list)
        if keys_list:
            self.assertEqual(list(rs), keys_list)
            self.assertEqual(list(rs.keys()), keys_list)
            self.assertEqual(
                list(rs.items()), list(zip(keys_list, records_list))
            )
            for keys in keys_list:
                self.assertIn(keys, rs)

    def test_keyless_schema(self):
        schema = records.RecordsSchema('test', data_column_name='more_data')
        engine = sqlite.create_engine('sqlite://')
        rs = records.Records(engine, schema)
        rs.create_all()
        rs.create_indices()

        self.assert_records(rs, [], [])

        rs.append(b'hello')
        self.assert_records(rs, [], [b'hello'])

        rs.append(b'world')
        self.assert_records(rs, [], [b'hello', b'world'])

        rs.extend([b'spam', b'egg'])
        self.assert_records(rs, [], [b'hello', b'world', b'spam', b'egg'])

        mq = lambda q, _: q
        for func, args in (
            (rs.__contains__, (1, )),
            (rs.__getitem__, (1, )),
            (rs.keys, ()),
            (rs.items, ()),
            (rs.get, (1, )),
            (rs.count, (mq, )),
            (rs.search_keys, (mq, )),
            (rs.search_records, (mq, )),
            (rs.search_items, (mq, )),
            (rs.insert, (1, b'')),
            (rs.update, ([(1, b'')], )),
        ):
            with self.subTest(func):
                with self.assertRaisesRegex(
                    AssertionError, r'expect non-empty'
                ):
                    # Call ``next`` in case ``func`` is a generator
                    # function (such as ``search``).
                    next(func(*args))

    def test_keyed_schema(self):
        schema = records.RecordsSchema(
            'test',
            (('key1', Integer), ('key2', String)),
        )
        engine = sqlite.create_engine('sqlite://')
        rs = records.Records(engine, schema)
        rs.create_all()
        rs.create_indices()

        self.assert_records(rs, [], [])

        rs[1, 'x'] = b'1x'
        self.assert_records(
            rs,
            [(1, 'x')],
            [b'1x'],
        )

        rs.insert((1, 'y'), b'1y')
        self.assert_records(
            rs,
            [(1, 'x'), (1, 'y')],
            [b'1x', b'1y'],
        )

        rs.update([((2, 'x'), b'2x'), ((2, 'y'), b'2y')])
        self.assert_records(
            rs,
            [(1, 'x'), (1, 'y'), (2, 'x'), (2, 'y')],
            [b'1x', b'1y', b'2x', b'2y'],
        )

        self.assertEqual(rs.get((1, 'x')), b'1x')
        self.assertEqual(rs.get((2, 'x')), b'2x')
        self.assertIsNone(rs.get((3, 'x')))
        self.assertEqual(rs.get((3, 'x'), 'nothing'), 'nothing')

        self.assertEqual(rs.count(lambda c: c.key1 == 1), 2)
        self.assertEqual(rs.count(lambda c: c.key1 == 2), 2)
        self.assertEqual(rs.count(), 4)
        self.assertEqual(
            list(rs.search_keys(lambda c: c.key1 == 1)),
            [(1, 'x'), (1, 'y')],
        )
        self.assertEqual(
            list(rs.search_records(lambda c: c.key1 == 1)),
            [b'1x', b'1y'],
        )
        self.assertEqual(
            list(rs.search_items(lambda c: c.key1 == 1)),
            [((1, 'x'), b'1x'), ((1, 'y'), b'1y')],
        )

        rs[1, 'z'] = b'1z'
        self.assertEqual(rs.count(lambda c: c.key1 == 1), 3)
        self.assertEqual(rs.count(lambda c: c.key1 == 2), 2)
        self.assertEqual(rs.count(), 5)
        self.assertEqual(
            list(rs.search_keys(lambda c: c.key1 == 1)),
            [(1, 'x'), (1, 'y'), (1, 'z')],
        )
        self.assertEqual(
            list(rs.search_records(lambda c: c.key1 == 1)),
            [b'1x', b'1y', b'1z'],
        )

        with self.assertRaises(KeyError):
            rs[3, '']  # pylint: disable=pointless-statement

        for func, args in (
            (rs.__contains__, (1, )),
            (rs.get, (1, )),
            (rs.__setitem__, (1, b'')),
            (rs.insert, (1, b'')),
            (rs.update, ([(1, b'')], )),
        ):
            with self.subTest(func):
                with self.assertRaisesRegex(
                    AssertionError, r'expect x == 2, not 1'
                ):
                    func(*args)

        for func, args in (
            (rs.append, (b'', )),
            (rs.extend, ([b''], )),
        ):
            with self.subTest(func):
                with self.assertRaisesRegex(AssertionError, r'expect empty'):
                    func(*args)

    def test_unique_constraint(self):
        schema = records.RecordsSchema('test', (('k', Integer), ))
        engine = sqlite.create_engine('sqlite://')
        rs = records.Records(engine, schema)
        rs.create_all()
        rs.create_indices()

        self.assert_records(rs, [], [])

        rs[1] = b'1'
        self.assert_records(rs, [(1, )], [b'1'])

        rs[1] = b'2'
        self.assert_records(rs, [(1, )], [b'2'])

        rs.insert(1, b'3')
        self.assert_records(rs, [(1, )], [b'3'])

        rs.update({1: b'4'})
        self.assert_records(rs, [(1, )], [b'4'])


if __name__ == '__main__':
    unittest.main()
