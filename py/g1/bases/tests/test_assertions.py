import unittest

from g1.bases.assertions import (
    Assertions,
    ASSERT,
)


class AssertionsTest(unittest.TestCase):

    assert_ = Assertions(AssertionError)

    def test_custom_exc_type(self):

        class CustomError(Exception):
            pass

        assertions = Assertions(CustomError)
        with self.assertRaises(CustomError):
            assertions.true(False)

    def test_unreachable(self):
        with self.assertRaisesRegex(AssertionError, 'error 1'):
            ASSERT.unreachable('error {}', 1)

    def test_assertion_methods_pass(self):
        checks = [
            ('__call__', (1, ''), 1),
            ('true', (True, ), True),
            ('true', (1, ), 1),
            ('false', (False, ), False),
            ('false', ('', ), ''),
            ('empty', ((), ), ()),
            ('empty', ([], ), []),
            ('empty', ({}, ), {}),
            ('empty', (set(), ), set()),
            ('not_empty', ((1, ), ), (1, )),
            ('not_empty', ([2], ), [2]),
            ('not_empty', (dict(x=1), ), dict(x=1)),
            ('not_empty', (set([42]), ), set([42])),
            ('none', (None, ), None),
            ('not_none', (0, ), 0),
            ('predicate', (0, is_even), 0),
            ('xor', (0, 1), 0),
            ('xor', (1, 0), 1),
            ('not_xor', (0, 0), 0),
            ('not_xor', (1, 1), 1),
            ('is_', (0, 0), 0),
            ('is_not', (0, 1), 0),
            ('isinstance', ('hello', (int, str)), 'hello'),
            ('not_isinstance', ('hello', (int, bytes)), 'hello'),
            ('issubclass', (Derived, Base), Derived),
            ('not_issubclass', (Base, Derived), Base),
            ('in_', (1, [1]), 1),
            ('not_in', (0, [1]), 0),
            ('contains', ([1], 1), [1]),
            ('not_contains', ([1], 0), [1]),
            ('equal', (0, 0), 0),
            ('not_equal', (0, 1), 0),
            ('greater', (1, 0), 1),
            ('greater_or_equal', (1, 0), 1),
            ('greater_or_equal', (0, 0), 0),
            ('less', (0, 1), 0),
            ('less_or_equal', (0, 1), 0),
            ('less_or_equal', (1, 1), 1),
            ('isdisjoint', ({1, 2}, {3, 4}), {1, 2}),
            ('not_isdisjoint', ({1, 2}, {2, 3, 4}), {1, 2}),
            ('issubset', ({1, 2}, {1, 2}), {1, 2}),
            ('not_issubset', ({1, 2}, {2, 3}), {1, 2}),
            ('issubset_proper', ({1, 2}, {1, 2, 3}), {1, 2}),
            ('not_issubset_proper', ({1, 2}, {1, 2}), {1, 2}),
            ('issuperset', ({1, 2}, {1, 2}), {1, 2}),
            ('not_issuperset', ({1, 2}, {2, 3}), {1, 2}),
            ('issuperset_proper', ({1, 2, 3}, {1, 2}), {1, 2, 3}),
            ('not_issuperset_proper', ({1, 2}, {1, 2}), {1, 2}),
        ]
        for check_name, args, expect_ret in checks:
            with self.subTest(check=check_name):
                check = getattr(ASSERT, check_name)
                self.assertEqual(check(*args), expect_ret)

    def test_assertion_methods_fail(self):
        with self.subTest(check='__call__'):
            pattern = r'some message 1'
            with self.assertRaisesRegex(AssertionError, pattern) as cm:
                self.assert_(False, 'some message {}', 1)
            self.assertEqual(cm.exception.args[1:], (False, ))
        with self.subTest(check='predicate'):
            pattern = r'expect .*is_even.*, not 1'
            with self.assertRaisesRegex(AssertionError, pattern) as cm:
                self.assert_.predicate(1, is_even)
            self.assertEqual(cm.exception.args[1:], (1, ))
        checks = [
            ('true', (0, ), r'expect true-value, not 0'),
            ('false', ('hello', ), r'expect false-value, not \'hello\''),
            ('empty', ([1], ), r'expect empty collection'),
            ('empty', (None, ), r'expect empty collection'),
            ('empty', (False, ), r'expect empty collection'),
            ('not_empty', ([], ), r'expect non-empty collection'),
            ('not_empty', (None, ), r'expect non-empty collection'),
            ('not_empty', (False, ), r'expect non-empty collection'),
            ('none', ('hello', ), r'expect None, not \'hello\''),
            ('not_none', (None, ), r'expect non-None value'),
            ('xor', (0, 0), r'expect 0 xor 0 be true'),
            ('xor', (1, 1), r'expect 1 xor 1 be true'),
            ('not_xor', (0, 1), r'expect 0 xor 1 be false'),
            ('not_xor', (1, 0), r'expect 1 xor 0 be false'),
            ('is_', (0, 1), r'expect 1, not 0'),
            ('is_not', (0, 0), r'expect non-0 value'),
            (
                'isinstance',
                ('x', int),
                r'expect <class \'int\'>-typed value, not \'x\'',
            ),
            (
                'not_isinstance',
                ('x', str),
                r'expect non-<class \'str\'>-typed value, but \'x\'',
            ),
            (
                'issubclass',
                (Base, Derived),
                r'expect subclass of .*Derived.*, not .*Base.*',
            ),
            (
                'not_issubclass',
                (Derived, Base),
                r'expect non-subclass of .*Base.*, but .*Derived.*',
            ),
            ('in_', (1, [0]), r'expect 1 in \[0\]'),
            ('not_in', (0, [0]), r'expect 0 not in \[0\]'),
            ('contains', ([0], 1), r'expect \[0\] containing 1'),
            ('not_contains', ([0], 0), r'expect \[0\] not containing 0'),
            ('not_contains', ([0], 0), r'expect \[0\] not containing 0'),
            ('equal', (0, 1), r'expect x == 1, not 0'),
            ('not_equal', (0, 0), r'expect x != 0, not 0'),
            ('greater', (0, 0), r'expect x > 0, not 0'),
            ('greater_or_equal', (-1, 0), r'expect x >= 0, not -1'),
            ('less', (0, 0), r'expect x < 0, not 0'),
            ('less_or_equal', (1, 0), r'expect x <= 0, not 1'),
            ('isdisjoint', ({1, 2}, {2, 3}), r'expect x.isdisjoint'),
            ('not_isdisjoint', ({1, 2}, {3, 4}), r'expect not x.isdisjoint'),
            ('issubset', ({1, 2}, {2, 3}), r'expect x.issubset'),
            ('not_issubset', ({1, 2}, {1, 2, 3}), r'expect not x.issubset'),
            (
                'issubset_proper',
                ({1, 2}, {2, 3}),
                r'expect x is proper subset of',
            ),
            (
                'not_issubset_proper',
                ({1, 2}, {1, 2, 3}),
                r'expect x is not proper subset of',
            ),
            ('issuperset', ({1, 2}, {2, 3}), r'expect x.issuperset'),
            (
                'not_issuperset',
                ({1, 2, 3}, {1, 2}),
                r'expect not x.issuperset',
            ),
            (
                'issuperset_proper',
                ({1, 2}, {2, 3}),
                r'expect x is proper superset of',
            ),
            (
                'not_issuperset_proper',
                ({1, 2, 3}, {1, 2}),
                r'expect x is not proper superset of',
            ),
        ]
        for check_name, args, pattern in checks:
            with self.subTest(check=check_name):
                check = getattr(self.assert_, check_name)
                with self.assertRaisesRegex(AssertionError, pattern) as cm:
                    check(*args)
                self.assertEqual(cm.exception.args[1:], args)

    def test_assert_collection_pass(self):
        checks = [
            ('all', (True, True, True)),
            ('not_all', (True, False, True)),
            ('not_all', (False, False, False)),
            ('any', (False, False, True)),
            ('any', (True, True, True)),
            ('not_any', (False, False, False)),
            ('only_one', (False, True, False)),
        ]
        for check_name, collection in checks:
            with self.subTest(check=check_name):
                check = getattr(ASSERT, check_name)
                self.assertEqual(check(collection), collection)

    def test_assert_collection_fail(self):
        checks = [
            ('all', (True, False, True)),
            ('not_all', (True, True, True)),
            ('any', (False, False, False)),
            ('not_any', (False, True, False)),
            ('only_one', (True, True, False)),
        ]
        for check_name, collection in checks:
            with self.subTest(check=check_name):
                check = getattr(self.assert_, check_name)
                with self.assertRaises(AssertionError) as cm:
                    check(collection)
                self.assertEqual(cm.exception.args[1:], (collection, ))

    def test_assert_collection_mapper(self):
        self.assertEqual(ASSERT.all([2, 4, 6], is_even), [2, 4, 6])
        pattern = r'expect all .*is_even.*, not \[2, 4, 6, 7\]'
        with self.assertRaisesRegex(AssertionError, pattern):
            ASSERT.all([2, 4, 6, 7], is_even)


class Base:
    pass


class Derived(Base):
    pass


def is_even(x):
    return x % 2 == 0


if __name__ == '__main__':
    unittest.main()
