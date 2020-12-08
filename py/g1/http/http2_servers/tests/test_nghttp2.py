import unittest

import ctypes

try:
    from g1.devtools import tests
except ImportError:
    tests = None

from g1.http.http2_servers import nghttp2


@unittest.skipUnless(tests, 'g1.tests unavailable')
@unittest.skipUnless(
    tests and tests.is_gcc_available() and tests.is_pkg_config_available(),
    'dependency unavailable',
)
class ConstantTest(unittest.TestCase, tests.CFixture if tests else object):

    HEADERS = ('nghttp2/nghttp2.h', )

    @classmethod
    def setUpClass(cls):
        cls.CFLAGS = tuple(
            tests.check_output(['pkg-config', '--cflags', 'libnghttp2']) \
            .decode('ascii')
            .split()
        )
        cls.LDFLAGS = tuple(
            tests.check_output(['pkg-config', '--libs', 'libnghttp2']) \
            .decode('ascii')
            .split()
        )

    def test_macro(self):
        var_defs = {
            'NGHTTP2_PROTO_VERSION_ID': str,
            'NGHTTP2_INITIAL_WINDOW_SIZE': int,
        }
        var_values = self.get_c_vars(var_defs)
        for macro_name, _ in var_defs.items():
            with self.subTest(macro_name):
                self.assertEqual(
                    getattr(nghttp2, macro_name),
                    var_values[macro_name],
                )

    def test_compound_types(self):
        self.assert_c_expr(
            ' && '.join(
                'sizeof(%s) == %d' % (
                    type_,
                    ctypes.sizeof(getattr(nghttp2, type_)),
                ) for type_ in (
                    # nghttp2_session is an incomplete type.
                    # 'nghttp2_session',
                    'nghttp2_data_source',
                    'nghttp2_frame_hd',
                    'nghttp2_data',
                    'nghttp2_nv',
                    'nghttp2_priority_spec',
                    'nghttp2_headers',
                    'nghttp2_rst_stream',
                    'nghttp2_push_promise',
                    'nghttp2_goaway',
                    'nghttp2_frame',
                    'nghttp2_info',
                    'nghttp2_settings_entry',
                    # nghttp2_session_callbacks is an incomplete type.
                    # 'nghttp2_session_callbacks',
                    'nghttp2_data_provider',
                )
            )
        )

    def test_enum(self):
        for py_enum_type in (
            nghttp2.nghttp2_error,
            nghttp2.nghttp2_nv_flag,
            nghttp2.nghttp2_frame_type,
            nghttp2.nghttp2_flag,
            nghttp2.nghttp2_settings_id,
            nghttp2.nghttp2_error_code,
            nghttp2.nghttp2_data_flag,
            nghttp2.nghttp2_headers_category,
        ):
            with self.subTest(py_enum_type):
                self.assertEqual(
                    self.get_enum_members(py_enum_type),
                    py_enum_type.__members__,
                )


if __name__ == '__main__':
    unittest.main()
