"""Unit test helper functions and fixtures.

Since this module is for testing our modules, it should not depend on
any of our modules.
"""

__all__ = [
    'check_call',
    'check_output',
    'check_program',
    'spawn',
    # Helpers for running C code.
    'CFixture',
    'is_gcc_available',
    'is_pkg_config_available',
]

import contextlib
import concurrent.futures
import io
import os
import subprocess
import sys
import tempfile
import threading


def spawn(func, *args, **kwargs):
    future = concurrent.futures.Future()
    thread = threading.Thread(target=_run, args=(future, func, args, kwargs))
    thread.start()
    return future


def _run(future, func, args, kwargs):
    if not future.set_running_or_notify_cancel():
        return
    try:
        result = func(*args, **kwargs)
    except BaseException as exc:
        future.set_exception(exc)
    else:
        future.set_result(result)


def check_call(args):
    try:
        subprocess.run(
            args,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        sys.stderr.buffer.write(exc.stderr)
        raise


def check_output(args):
    try:
        proc = subprocess.run(
            args,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return proc.stdout
    except subprocess.CalledProcessError as exc:
        sys.stderr.buffer.write(exc.stderr)
        raise


def check_program(args):
    try:
        check_call(args)
    except FileNotFoundError:
        return False
    else:
        return True


def is_gcc_available():
    """True if `gcc` is available."""
    return check_program(['gcc', '--version'])


def is_pkg_config_available():
    """True if `pkg-config` is available."""
    return check_program(['pkg-config', '--version'])


class CFixture:
    """Fixture for running C code."""

    HEADERS = ()
    CFLAGS = ()
    LDFLAGS = ()

    def run_c_code(self, code):
        """Run C code and return its stdout."""
        with contextlib.ExitStack() as stack:
            # Use ``mkstemp`` rather than ``NamedTemporaryFile`` so that
            # we may execute it.
            fd, src_path = tempfile.mkstemp(suffix='.c', text=True)
            stack.callback(os.remove, src_path)
            with os.fdopen(fd, 'w') as f:
                f.write(code)
            exe_path = src_path + '.out'
            stack.callback(_maybe_remove, exe_path)
            check_call([
                'gcc', *self.CFLAGS, src_path, '-o', exe_path, *self.LDFLAGS
            ])
            os.chmod(exe_path, 0o755)
            return check_output([exe_path])

    def assert_c_expr(self, c_expr):
        """Assert a C expression is evaluated to true."""
        code = io.StringIO()
        code.write('#include <stdio.h>\n')
        for header in self.HEADERS:
            code.write('#include <%s>\n' % header)
        code.write('int main() { return !(%s); }' % c_expr)
        self.run_c_code(code.getvalue())

    def get_c_vars(self, names_types):
        """Read C variable values from header files."""

        code = io.StringIO()

        code.write('#include <stdio.h>\n')
        for header in self.HEADERS:
            code.write('#include <%s>\n' % header)

        code.write('int main() {')

        first = True
        for name, type_ in names_types.items():

            if not first:
                code.write('putchar(0);')
            first = False

            code.write('fputs("%s", stdout);' % name)

            code.write('putchar(0);')

            assert type_ in (int, str)
            if type_ is int:
                code.write('printf("%%d", %s);' % name)
            elif type_ is str:
                code.write('fputs(%s, stdout);' % name)
            else:
                raise AssertionError('unsupported type: %s' % type_)

        code.write('return 0;}')

        output = self.run_c_code(code.getvalue())

        if output:
            fields = [f.decode('ascii') for f in output.split(b'\0')]
        else:  # Special case when output == b''.
            fields = []
        assert len(fields) % 2 == 0

        values = {}
        for i in range(0, len(fields), 2):
            name = fields[i]
            type_ = names_types[name]
            assert name not in values
            values[name] = type_(fields[i + 1])
        assert len(values) == len(names_types)

        return values

    def get_enum_members(self, py_enum_type):
        # ``__members__`` gives you all - even aliases.
        values = self.get_c_vars({n: int for n in py_enum_type.__members__})
        return {name: py_enum_type(value) for name, value in values.items()}


def _maybe_remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
