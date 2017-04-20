import unittest

from garage import asserts


class AssertsTest(unittest.TestCase):

    def test_asserts(self):

        asserts.precond(True)
        asserts.postcond(True)

        tests = [
            (asserts.true, (True, 1, 'x', [1])),
            (asserts.not_true, (False, None, 0, '', [], ())),
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
            asserts.precond(False)
        with self.assertRaises(AssertionError):
            asserts.postcond(False)

        tests = [
            (asserts.true, (False, None, 0, '', [], ())),
            (asserts.not_true, (True, 1, 'x', [1])),
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


if __name__ == '__main__':
    unittest.main()
