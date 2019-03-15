import unittest

from g1 import tests
from g1.http.servers import nghttp2


@unittest.skipUnless(
    tests.is_gcc_available() and tests.is_pkg_config_available(),
    'dependency unavailable',
)
class ConstantTest(unittest.TestCase, tests.CFixture):

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
                members = self.get_enum_members(py_enum_type)
                self.assertEqual(members, py_enum_type.__members__)
                # Enum members are re-exported to the global scope.
                for name, member in py_enum_type.__members__.items():
                    self.assertIs(getattr(nghttp2, name), member)


class ExportedNamesTest(unittest.TestCase):

    def test_exported_names(self):
        for name in nghttp2.__all__:
            with self.subTest(name):
                self.assertTrue(name.lower().startswith('nghttp2'))
                self.assertTrue(hasattr(nghttp2, name))


if __name__ == '__main__':
    unittest.main()
