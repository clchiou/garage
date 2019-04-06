import unittest

import ctypes
import os

try:
    from g1.devtools import tests
except ImportError:
    tests = None

from nng import _nng

CFLAGS = os.environ.get('CFLAGS')
LDFLAGS = os.environ.get('LDFLAGS')


@unittest.skipUnless(tests, 'g1.tests unavailable')
@unittest.skipUnless(tests and tests.is_gcc_available(), 'gcc unavailable')
@unittest.skipUnless(CFLAGS and LDFLAGS, 'CFLAGS or LDFLAGS not set')
class EnumTest(unittest.TestCase, tests.CFixture if tests else object):

    HEADERS = (
        'nng/nng.h',
        'nng/protocol/pair1/pair.h',
        'nng/protocol/pubsub0/sub.h',
        'nng/protocol/reqrep0/req.h',
        'nng/protocol/survey0/survey.h',
    )
    CFLAGS = (CFLAGS or '').split()
    LDFLAGS = (LDFLAGS or '').split()

    def test_types(self):
        self.assert_c_expr(
            ' && '.join(
                'sizeof(%s) == %d' % (
                    type_,
                    ctypes.sizeof(getattr(_nng, type_)),
                ) for type_ in (
                    # Handle type.
                    'nng_ctx',
                    'nng_dialer',
                    'nng_listener',
                    'nng_pipe',
                    'nng_socket',
                    # Union type.
                    'nng_sockaddr',
                )
            )
        )

    def test_constants(self):
        expect = {
            n: getattr(_nng, n)
            for n in (
                'NNG_DURATION_INFINITE',
                'NNG_DURATION_DEFAULT',
                'NNG_DURATION_ZERO',
                'NNG_MAXADDRLEN',
            )
        }
        actual = self.get_c_vars({n: type(v) for n, v in expect.items()})
        self.assertEqual(actual, expect)

    def test_enums(self):
        for py_enum_type in (
            _nng.nng_sockaddr_family,
            _nng.nng_flag_enum,
            _nng.nng_errno_enum,
        ):
            with self.subTest(py_enum_type):
                self.assertEqual(
                    self.get_enum_members(py_enum_type),
                    py_enum_type.__members__,
                )

    def test_options(self):
        actual = self.get_c_vars({option.name: str for option in _nng.Options})
        expect = {
            option.name: option.value[0].decode('ascii')
            for option in _nng.Options
        }
        self.assertEqual(actual, expect)


if __name__ == '__main__':
    unittest.main()
