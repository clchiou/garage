import unittest

from garage.assertions import ASSERT


class AssertsTest(unittest.TestCase):

    def test_asserts(self):

        tests = [
            (ASSERT.true, (True, 1, 'x', [1])),
            (ASSERT.false , (False, None, 0, '', [], ())),
            (ASSERT.none, (None,)),
            (ASSERT.not_none, (True, False, 0, 1, [], (), '')),
        ]
        for assertion, values in tests:
            for value in values:
                self.assertEqual(value, assertion(value))

        self.assertEqual(0, ASSERT.type_of(0, int))
        self.assertEqual('', ASSERT.type_of('', str))
        self.assertEqual('', ASSERT.not_type_of('', int))
        self.assertEqual(0, ASSERT.not_type_of(0, str))

        self.assertEqual('', ASSERT.equal('', ''))
        self.assertEqual(1, ASSERT.equal(1, 1))
        self.assertEqual('', ASSERT.not_equal('', 1))
        self.assertEqual(1, ASSERT.not_equal(1, ''))

        with self.assertRaises(AssertionError):
            ASSERT.fail('')
        with self.assertRaises(AssertionError):
            ASSERT(False, '')

        tests = [
            (ASSERT.true, (False, None, 0, '', [], ())),
            (ASSERT.false, (True, 1, 'x', [1])),
            (ASSERT.none, (True, False, 0, 1, [], (), '')),
            (ASSERT.not_none, (None,)),
        ]
        for assertion, values in tests:
            for value in values:
                with self.assertRaisesRegex(AssertionError, r'expect .*'):
                    assertion(value)

        with self.assertRaisesRegex(AssertionError, r'expect .*'):
            ASSERT.type_of(0, str)
        with self.assertRaisesRegex(AssertionError, r'expect .*'):
            ASSERT.not_type_of('', str)

        with self.assertRaisesRegex(AssertionError, r'expect .*'):
            ASSERT.equal(0, '')
        with self.assertRaisesRegex(AssertionError, r'expect .*'):
            ASSERT.not_equal(0, 0)

        tests = [
            (ASSERT.in_, (1, [1])),
            (ASSERT.not_in, (1, [2])),
            (ASSERT.is_, (1, 1)),
            (ASSERT.is_not, (1, 2)),
            (ASSERT.greater, (2, 1)),
            (ASSERT.greater_or_equal, (2, 1)),
            (ASSERT.greater_or_equal, (2, 2)),
            (ASSERT.less, (1, 2)),
            (ASSERT.less_or_equal, (1, 2)),
            (ASSERT.less_or_equal, (1, 1)),
        ]
        for assertions, args in tests:
            self.assertEqual(args[0], assertions(*args))

        tests = [
            (ASSERT.in_, (1, [2])),
            (ASSERT.not_in, (1, [1])),
            (ASSERT.is_, (1, 2)),
            (ASSERT.is_not, (1, 1)),
            (ASSERT.greater, (1, 2)),
            (ASSERT.greater_or_equal, (1, 2)),
            (ASSERT.less, (2, 1)),
            (ASSERT.less_or_equal, (2, 1)),
        ]
        for assertions, args in tests:
            with self.assertRaises(AssertionError):
                assertions(*args)


if __name__ == '__main__':
    unittest.main()
