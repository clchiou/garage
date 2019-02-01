import unittest

import os
import subprocess
import tempfile

from g1.http.servers import nghttp2


def check_call(command):
    return subprocess.check_call(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def check_output(command):
    return subprocess.check_output(
        command,
        stderr=subprocess.DEVNULL,
    )


def check_program(command):
    try:
        return check_call(command) == 0
    except FileNotFoundError:
        return False


GCC_AVAILABLE = check_program(['gcc', '--version'])
PKG_CONFIG_AVAILABLE = check_program(['pkg-config', '--version'])

DEPENDENCY_AVAILABLE = GCC_AVAILABLE and PKG_CONFIG_AVAILABLE


class Fixture:

    @classmethod
    def setUpClass(cls):
        cmd = ['pkg-config', '--cflags', 'libnghttp2']
        cls.nghttp2_cflags = check_output(cmd).decode('ascii').split()
        cmd = ['pkg-config', '--libs', 'libnghttp2']
        cls.nghttp2_libs = check_output(cmd).decode('ascii').split()

    def read_vars(self, var_defs):
        # Use ``mkstemp`` rather than ``NamedTemporaryFile`` so that we
        # may execute it.
        fd, src_path = tempfile.mkstemp(suffix='.c')
        os.close(fd)
        exe_path = src_path + '.out'
        try:

            with open(src_path, 'w') as src_file:
                src_file.write(
                    '#include <stdio.h>\n'
                    '#include <nghttp2/nghttp2.h>\n'
                    'int main() {\n'
                )
                fmts = {int: '%d', str: '%s'}
                for var_name, var_type in var_defs.items():
                    src_file.write(
                        '    printf("{0} {1}\\n", {0});\n'.format(
                            var_name,
                            fmts[var_type],
                        )
                    )
                src_file.write('    return 0;\n}\n')

            compile_command = ['gcc', src_path, '-o', exe_path]
            compile_command.extend(self.nghttp2_cflags)
            compile_command.extend(self.nghttp2_libs)
            check_call(compile_command)

            os.chmod(exe_path, 0o755)

            var_values = {}
            converters = {
                int: int,
                str: lambda x: x,
            }
            for line in check_output([exe_path]).decode('ascii').split('\n'):
                if line:
                    var_name, var_value = line.split(maxsplit=1)
                    var_type = var_defs[var_name]
                    var_values[var_name] = converters[var_type](var_value)

            return var_values

        finally:
            os.remove(src_path)
            os.remove(exe_path)


@unittest.skipUnless(DEPENDENCY_AVAILABLE, 'dependency unavailable')
class ConstantTest(Fixture, unittest.TestCase):

    def test_macro(self):
        var_defs = {
            'NGHTTP2_PROTO_VERSION_ID': str,
            'NGHTTP2_INITIAL_WINDOW_SIZE': int,
        }
        var_values = self.read_vars(var_defs)
        for macro_name, _ in var_defs.items():
            with self.subTest(macro_name):
                self.assertEqual(
                    getattr(nghttp2, macro_name),
                    var_values[macro_name],
                )

    def test_enum(self):
        testdata = [
            (int, nghttp2.nghttp2_error),
            (int, nghttp2.nghttp2_nv_flag),
            (int, nghttp2.nghttp2_frame_type),
            (int, nghttp2.nghttp2_flag),
            (int, nghttp2.nghttp2_settings_id),
            (int, nghttp2.nghttp2_error_code),
            (int, nghttp2.nghttp2_data_flag),
            (int, nghttp2.nghttp2_headers_category),
        ]
        var_values = self.read_vars({
            member.name: var_type
            for var_type, enum_type in testdata for member in enum_type
        })
        for _, enum_type in testdata:
            for member in enum_type:
                with self.subTest(member.name):
                    self.assertEqual(member, var_values[member.name])
                    # Enum members are re-exported to the global scope.
                    self.assertIs(getattr(nghttp2, member.name), member)


class ExportedNamesTest(unittest.TestCase):

    def test_exported_names(self):
        for name in nghttp2.__all__:
            with self.subTest(name):
                self.assertTrue(name.lower().startswith('nghttp2'))
                self.assertTrue(hasattr(nghttp2, name))


if __name__ == '__main__':
    unittest.main()
