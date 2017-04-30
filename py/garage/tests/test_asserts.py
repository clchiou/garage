import unittest

from garage import asserts


class AssertsTest(unittest.TestCase):

    def test_asserts(self):

        asserts.precond(True, '')
        asserts.postcond(True, '')

        tests = [
            (asserts.true, (True, 1, 'x', [1])),
            (asserts.false , (False, None, 0, '', [], ())),
            (asserts.none, (None,)),
            (asserts.not_none, (True, False, 0, 1, [], (), '')),
        ]
        for assertion, values in tests:
            for value in values:
                self.assertEqual(value, assertion(value))

        self.assertEqual(0, asserts.type_of(0, int))
        self.assertEqual('', asserts.type_of('', str))
        self.assertEqual('', asserts.not_type_of('', int))
        self.assertEqual(0, asserts.not_type_of(0, str))

        self.assertEqual('', asserts.equal('', ''))
        self.assertEqual(1, asserts.equal(1, 1))
        self.assertEqual('', asserts.not_equal('', 1))
        self.assertEqual(1, asserts.not_equal(1, ''))

        with self.assertRaises(AssertionError):
            asserts.precond(False, '')
        with self.assertRaises(AssertionError):
            asserts.postcond(False, '')

        tests = [
            (asserts.true, (False, None, 0, '', [], ())),
            (asserts.false, (True, 1, 'x', [1])),
            (asserts.none, (True, False, 0, 1, [], (), '')),
            (asserts.not_none, (None,)),
        ]
        for assertion, values in tests:
            for value in values:
                with self.assertRaisesRegex(AssertionError, r'expect .*'):
                    assertion(value)

        with self.assertRaisesRegex(AssertionError, r'expect .*'):
            asserts.type_of(0, str)
        with self.assertRaisesRegex(AssertionError, r'expect .*'):
            asserts.not_type_of('', str)

        with self.assertRaisesRegex(AssertionError, r'expect .*'):
            asserts.equal(0, '')
        with self.assertRaisesRegex(AssertionError, r'expect .*'):
            asserts.not_equal(0, 0)

        tests = [
            (asserts.in_, (1, [1])),
            (asserts.not_in, (1, [2])),
            (asserts.is_, (1, 1)),
            (asserts.is_not, (1, 2)),
            (asserts.greater, (2, 1)),
            (asserts.greater_or_equal, (2, 1)),
            (asserts.greater_or_equal, (2, 2)),
            (asserts.less, (1, 2)),
            (asserts.less_or_equal, (1, 2)),
            (asserts.less_or_equal, (1, 1)),
        ]
        for assertions, args in tests:
            self.assertEqual(args[0], assertions(*args))

        tests = [
            (asserts.in_, (1, [2])),
            (asserts.not_in, (1, [1])),
            (asserts.is_, (1, 2)),
            (asserts.is_not, (1, 1)),
            (asserts.greater, (1, 2)),
            (asserts.greater_or_equal, (1, 2)),
            (asserts.less, (2, 1)),
            (asserts.less_or_equal, (2, 1)),
        ]
        for assertions, args in tests:
            with self.assertRaises(AssertionError):
                assertions(*args)


if __name__ == '__main__':
    unittest.main()
