import unittest

from nanomsg import errors
from nanomsg.constants import Error


class ErrorsTest(unittest.TestCase):

    def test_errors(self):

        varz = vars(errors)
        lookup_table = varz['_ERRORS']

        for error in Error:

            self.assertIn(error.name, errors.__all__)
            self.assertIn(error.name, varz)

            exc_class = varz[error.name]
            self.assertTrue(issubclass(exc_class, errors.NanomsgError))

            self.assertIs(exc_class, lookup_table[error])

            # Look up by Error.
            exc = errors.NanomsgError.make(error)
            self.assertIsInstance(exc, exc_class)
            self.assertEqual(error, exc.error)

            # Look up by int errno value.
            exc = errors.NanomsgError.make(error.value)
            self.assertIsInstance(exc, exc_class)
            self.assertEqual(error, exc.error)

            # No such errno.
            exc = errors.NanomsgError.make(999)
            self.assertIsInstance(exc, errors.NanomsgError)
            self.assertEqual(999, exc.error)


if __name__ == '__main__':
    unittest.main()
