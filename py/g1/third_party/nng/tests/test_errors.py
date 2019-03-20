import unittest

from nng import _nng
from nng import errors


class NngErrorTest(unittest.TestCase):

    def test_error(self):
        for errno in _nng.nng_errno_enum:
            with self.subTest(errno=errno):
                error = errors.make_exc(errno)
                error = errors.make_exc(errno)
                self.assertIsInstance(error, errors.NngError)
                if errno in (
                    _nng.nng_errno_enum.NNG_ESYSERR,
                    _nng.nng_errno_enum.NNG_ETRANERR,
                ):
                    self.assertEqual(error.args[0], errno)
                else:
                    self.assertEqual(error.errno, errno)
                self.assertEqual(
                    str(error),
                    '%s: %s' % (
                        errno.name,
                        _nng.F.nng_strerror(errno).decode('utf8'),
                    ),
                )

    def test_unknown_error(self):
        errno = 9999
        with self.assertRaises(ValueError):
            _nng.nng_errno_enum(errno)
        error = errors.make_exc(errno)
        self.assertIsInstance(error, errors.UnknownError)
        self.assertEqual(str(error), r'Unknown error #9999')


if __name__ == '__main__':
    unittest.main()
