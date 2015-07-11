import unittest

import garage.preconds
from garage.preconds import IllegalArgumentException
from garage.preconds import IllegalStateException


class TestPreconds(unittest.TestCase):

    def test_preconds(self):
        for exc, check in (
                (IllegalArgumentException, garage.preconds.check_arg),
                (IllegalStateException, garage.preconds.check_state)):
            with self.assertRaisesRegex(exc, r'^$', msg=check.__name__):
                check(False)
            with self.assertRaisesRegex(exc, r'^Message$', msg=check.__name__):
                check(False, 'Message')
            with self.assertRaisesRegex(exc, r'^X Y$', msg=check.__name__):
                check(False, 'X %s', 'Y')

        garage.preconds.check_arg(True)
        garage.preconds.check_arg(True, 'Message')
        garage.preconds.check_arg(True, 'Message: %s', 'Hello world')

        garage.preconds.check_state(True)
        garage.preconds.check_state(True, 'Message')
        garage.preconds.check_state(True, 'Message: %s', 'Hello world')


if __name__ == '__main__':
    unittest.main()
