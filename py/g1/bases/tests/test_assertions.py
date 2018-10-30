import unittest

from g1.bases.assertions import (
    Assertions,
    ASSERT,
)


class AssertionsTest(unittest.TestCase):

    def test_custom_exc_type(self):

        class CustomError(Exception):
            pass

        assertions = Assertions(CustomError)
        with self.assertRaises(CustomError):
            assertions.true(False)

    def test_assertion_methods_pass(self):
        checks = [
            ('__call__', (1, ''), 1),
            ('true', (True, ), True),
            ('true', (1, ), 1),
            ('false', (False, ), False),
            ('false', ('', ), ''),
            ('none', (None, ), None),
            ('not_none', (0, ), 0),
            ('is_', (0, 0), 0),
            ('is_not', (0, 1), 0),
            ('type_of', ('hello', (int, str)), 'hello'),
            ('not_type_of', ('hello', (int, bytes)), 'hello'),
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
        ]
        for check_name, args, expect_ret in checks:
            with self.subTest(check=check_name):
                check = getattr(ASSERT, check_name)
                self.assertEqual(check(*args), expect_ret)

    def test_assertion_methods_fail(self):
        with self.subTest(check='__call__'):
            pattern = r'some message 1'
            with self.assertRaisesRegex(AssertionError, pattern) as cm:
                ASSERT(False, 'some message {}', 1)
            self.assertEqual(cm.exception.args[1:], (False, ))
        checks = [
            ('true', (0, ), r'expect true-value, not 0'),
            ('false', ('hello', ), r'expect false-value, not \'hello\''),
            ('none', ('hello', ), r'expect None, not \'hello\''),
            ('not_none', (None, ), r'expect non-None value'),
            ('is_', (0, 1), r'expect 1, not 0'),
            ('is_not', (0, 0), r'expect non-0 value'),
            (
                'type_of',
                ('x', int),
                r'expect <class \'int\'>-typed value, not \'x\'',
            ),
            (
                'not_type_of',
                ('x', str),
                r'expect non-<class \'str\'>-typed value, but \'x\'',
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
        ]
        for check_name, args, pattern in checks:
            with self.subTest(check=check_name):
                check = getattr(ASSERT, check_name)
                with self.assertRaisesRegex(AssertionError, pattern) as cm:
                    check(*args)
                self.assertEqual(cm.exception.args[1:], args)


if __name__ == '__main__':
    unittest.main()
