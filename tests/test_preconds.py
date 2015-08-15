import unittest

from garage import preconds
from garage.preconds import IllegalArgumentException
from garage.preconds import IllegalStateException


class PrecondsTest(unittest.TestCase):

    def test_preconds(self):
        for exc, check in (
                (IllegalArgumentException, preconds.check_argument),
                (IllegalStateException, preconds.check_state)):
            with self.assertRaisesRegex(exc, r'^$', msg=check.__name__):
                check(False)
            with self.assertRaisesRegex(exc, r'^Message$', msg=check.__name__):
                check(False, 'Message')
            with self.assertRaisesRegex(exc, r'^X Y$', msg=check.__name__):
                check(False, 'X %s', 'Y')

        preconds.check_argument(True)
        preconds.check_argument(True, 'Message')
        preconds.check_argument(True, 'Message: %s', 'Hello world')

        preconds.check_state(True)
        preconds.check_state(True, 'Message')
        preconds.check_state(True, 'Message: %s', 'Hello world')


if __name__ == '__main__':
    unittest.main()
