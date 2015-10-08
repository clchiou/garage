import unittest

from garage import asserts


class PrecondsTest(unittest.TestCase):

    def test_preconds(self):
        for exc, check in (
                (AssertionError, asserts.precond),
                (AssertionError, asserts.postcond)):
            with self.assertRaisesRegex(exc, r'^$', msg=check.__name__):
                check(False)
            with self.assertRaisesRegex(exc, r'^Message$', msg=check.__name__):
                check(False, 'Message')
            with self.assertRaisesRegex(exc, r'^X Y$', msg=check.__name__):
                check(False, 'X %s', 'Y')

        asserts.precond(True)
        asserts.precond(True, 'Message')
        asserts.precond(True, 'Message: %s', 'Hello world')

        asserts.postcond(True)
        asserts.postcond(True, 'Message')
        asserts.postcond(True, 'Message: %s', 'Hello world')


if __name__ == '__main__':
    unittest.main()
