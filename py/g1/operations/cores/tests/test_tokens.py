import unittest
import unittest.mock

import tempfile
from pathlib import Path

from g1.operations.cores import tokens


class DefinitionTest(unittest.TestCase):

    def test_post_init(self):
        with self.assertRaises(AssertionError):
            tokens.Tokens.Definition(kind='no-such-kind', args=[])

        with self.assertRaises(AssertionError):
            tokens.Tokens.Definition(kind='range', args=[])
        with self.assertRaises(AssertionError):
            tokens.Tokens.Definition(kind='range', args=[1, 0])

        with self.assertRaises(AssertionError):
            tokens.Tokens.Definition(kind='values', args=[0, 1])

    def test_validate_assigned_values(self):
        d = tokens.Tokens.Definition(kind='range', args=[0, 0])
        d.validate_assigned_values([])
        with self.assertRaises(AssertionError):
            d.validate_assigned_values(['0'])

        d = tokens.Tokens.Definition(kind='range', args=[0, 1])
        d.validate_assigned_values([])
        d.validate_assigned_values(['0'])
        with self.assertRaises(AssertionError):
            d.validate_assigned_values(['1'])

        d = tokens.Tokens.Definition(kind='values', args=[])
        d.validate_assigned_values([])
        with self.assertRaises(AssertionError):
            d.validate_assigned_values(['x'])

        d = tokens.Tokens.Definition(kind='values', args=['x', 'x'])
        d.validate_assigned_values([])
        d.validate_assigned_values(['x'])
        d.validate_assigned_values(['x', 'x'])
        with self.assertRaises(AssertionError):
            d.validate_assigned_values(['x', 'x', 'x'])
        with self.assertRaises(AssertionError):
            d.validate_assigned_values(['y'])

    def test_next_available(self):
        d = tokens.Tokens.Definition(kind='range', args=[0, 0])
        with self.assertRaises(AssertionError):
            d.next_available([])

        d = tokens.Tokens.Definition(kind='range', args=[0, 1])
        self.assertEqual(d.next_available([]), '0')
        with self.assertRaises(AssertionError):
            d.next_available(['0'])

        d = tokens.Tokens.Definition(kind='values', args=[])
        with self.assertRaises(AssertionError):
            d.next_available([])

        d = tokens.Tokens.Definition(kind='values', args=['x', 'x'])
        self.assertEqual(d.next_available([]), 'x')
        self.assertEqual(d.next_available(['x']), 'x')
        with self.assertRaises(AssertionError):
            d.next_available(['x', 'x'])


class TokensTest(unittest.TestCase):

    POD_ID_1 = '00000000-0000-0000-0000-000000000001'
    POD_ID_2 = '00000000-0000-0000-0000-000000000002'

    DEFINITIONS = {
        'x': tokens.Tokens.Definition(kind='range', args=[0, 1]),
        'y': tokens.Tokens.Definition(kind='values', args=['p', 'q']),
    }

    @staticmethod
    def make_assignments(*args):
        return [
            tokens.Tokens.Assignment(
                pod_id=args[i],
                name='foo',
                value=args[i + 1],
            ) for i in range(0, len(args), 2)
        ]

    def test_dump_and_load(self):
        t = tokens.Tokens(
            definitions=self.DEFINITIONS,
            assignments={
                'x': self.make_assignments(self.POD_ID_1, '0'),
                'y':
                self.make_assignments(self.POD_ID_1, 'p', self.POD_ID_2, 'q'),
            },
        )
        with tempfile.NamedTemporaryFile() as tokens_tempfile:
            tokens_path = Path(tokens_tempfile.name)
            t.dump(tokens_path)
            self.assertEqual(tokens.Tokens.load(tokens_path), t)

    def test_check_invariants(self):
        with self.assertRaises(AssertionError):
            tokens.Tokens(
                definitions={},
                assignments={'invalid-name': []},
            )
        with self.assertRaises(AssertionError):
            tokens.Tokens(
                definitions=self.DEFINITIONS,
                assignments={'no_such_token': []},
            )
        with self.assertRaises(AssertionError):
            tokens.Tokens(
                definitions=self.DEFINITIONS,
                assignments={
                    'x':
                    self.make_assignments(
                        self.POD_ID_1, '1', self.POD_ID_2, '1'
                    ),
                },
            )
        with self.assertRaises(AssertionError):
            tokens.Tokens(
                definitions=self.DEFINITIONS,
                assignments={
                    'y':
                    self.make_assignments(
                        self.POD_ID_1, 'p', self.POD_ID_2, 'p'
                    ),
                },
            )

    def test_assign(self):
        t = tokens.Tokens(definitions=self.DEFINITIONS, assignments={})
        self.assertEqual(t.assignments, {})

        with self.assertRaises(AssertionError):
            t.assign('no_such_token', self.POD_ID_1, 'x1')
        self.assertEqual(t.assignments, {})

        self.assertEqual(t.assign('x', self.POD_ID_1, 'foo'), '0')
        t.check_invariants()
        self.assertEqual(
            t.assignments, {
                'x': self.make_assignments(self.POD_ID_1, '0'),
            }
        )

        with self.assertRaises(AssertionError):
            t.assign('x', self.POD_ID_2, 'foo')
        self.assertEqual(
            t.assignments, {
                'x': self.make_assignments(self.POD_ID_1, '0'),
            }
        )

    def test_unassign(self):
        t = tokens.Tokens(
            definitions=self.DEFINITIONS,
            assignments={
                'x': self.make_assignments(self.POD_ID_1, '0'),
                'y': self.make_assignments(self.POD_ID_1, 'p'),
            },
        )
        t.unassign('x', self.POD_ID_1, 'foo')
        t.check_invariants()
        self.assertEqual(
            t.assignments,
            {'y': self.make_assignments(self.POD_ID_1, 'p')},
        )

    def test_unassign_all(self):
        t = tokens.Tokens(
            definitions=self.DEFINITIONS,
            assignments={
                'x': self.make_assignments(self.POD_ID_1, '0'),
                'y':
                self.make_assignments(self.POD_ID_1, 'p', self.POD_ID_2, 'q'),
            },
        )
        t.unassign_all(self.POD_ID_1)
        t.check_invariants()
        self.assertEqual(
            t.assignments,
            {'y': self.make_assignments(self.POD_ID_2, 'q')},
        )

    def test_cleanup(self):
        t = tokens.Tokens(
            definitions=self.DEFINITIONS,
            assignments={
                'x': self.make_assignments(self.POD_ID_1, '0'),
                'y':
                self.make_assignments(self.POD_ID_1, 'p', self.POD_ID_2, 'q'),
            },
        )
        t.cleanup({self.POD_ID_1})
        t.check_invariants()
        self.assertEqual(
            t.assignments,
            {
                'x': self.make_assignments(self.POD_ID_1, '0'),
                'y': self.make_assignments(self.POD_ID_1, 'p'),
            },
        )


class TokensDatabaseTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        unittest.mock.patch(tokens.__name__ + '.bases.set_file_attrs').start()

    def tearDown(self):
        unittest.mock.patch.stopall()
        super().tearDown()

    def test_database(self):
        with tempfile.NamedTemporaryFile() as tokens_tempfile:
            tokens_path = Path(tokens_tempfile.name)
            tokens.Tokens(definitions={}, assignments={}).dump(tokens_path)
            db = tokens.TokensDatabase(tokens_path)
            self.assertEqual(
                db.get(),
                tokens.Tokens(definitions={}, assignments={}),
            )
            d = tokens.Tokens.Definition(kind='values', args=['c'])
            pod_id = '00000000-0000-0000-0000-000000000001'
            with db.writing() as t:
                t.add_definition('x', d)
                t.assign('x', pod_id, 'x1')
            self.assertEqual(
                db.get(),
                tokens.Tokens(
                    definitions={'x': d},
                    assignments={
                        'x': [
                            tokens.Tokens.Assignment(
                                pod_id=pod_id, name='x1', value='c'
                            ),
                        ],
                    },
                ),
            )

    def test_abort(self):
        with tempfile.NamedTemporaryFile() as tokens_tempfile:
            tokens_path = Path(tokens_tempfile.name)
            tokens.Tokens(definitions={}, assignments={}).dump(tokens_path)
            db = tokens.TokensDatabase(tokens_path)
            self.assertEqual(
                db.get(),
                tokens.Tokens(definitions={}, assignments={}),
            )
            d = tokens.Tokens.Definition(kind='values', args=['c'])
            pod_id = '00000000-0000-0000-0000-000000000001'
            try:
                with db.writing() as t:
                    t.add_definition('x', d)
                    t.assign('x', pod_id, 'x1')
                    raise RuntimeError
            except RuntimeError:
                pass
            self.assertEqual(
                db.get(),
                tokens.Tokens(definitions={}, assignments={}),
            )


if __name__ == '__main__':
    unittest.main()
