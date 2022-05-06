import unittest

import ctypes
import errno
import os
import tempfile
from pathlib import Path

from g1.files import xattrs
from g1.files import _xattrs


class XattrsTestBase(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self._tempfile = tempfile.NamedTemporaryFile()  # pylint: disable=consider-using-with
        self._temp_symlink = self._tempfile.name + '-symlink'
        os.symlink(self._tempfile.name, self._temp_symlink)
        self.temp_path = Path(self._tempfile.name)
        self.temp_path_str = self._tempfile.name
        self.temp_path_bytes = self._tempfile.name.encode('ascii')
        self.temp_symlink = self._temp_symlink.encode('ascii')
        self.temp_fd = self._tempfile.fileno()

    def tearDown(self):
        self._tempfile.close()
        os.unlink(self._temp_symlink)
        super().tearDown()

    def assert_listxattr(self, expect_regular):

        for listxattr, path, expect in [
            (_xattrs.listxattr, self.temp_path_bytes, expect_regular),
            (_xattrs.listxattr, self.temp_symlink, expect_regular),
            (_xattrs.llistxattr, self.temp_symlink, b''),
            (_xattrs.flistxattr, self.temp_fd, expect_regular),
        ]:
            with self.subTest((listxattr, path, expect)):
                buffer = ctypes.create_string_buffer(len(expect) + 10)
                self.assertEqual(
                    listxattr(path, buffer, len(buffer)),
                    len(expect),
                )
                self.assertEqual(buffer.raw[:len(expect)], expect)

        expect_bytes = expect_regular.split(b'\x00')
        expect_str = [x.decode('utf-8') for x in expect_bytes]
        for path in [
            self.temp_path,
            self.temp_path_bytes,
            self.temp_path_str,
            self.temp_fd,
        ]:
            with self.subTest(path):
                self.assertEqual(
                    xattrs.listxattr(path, encoding=None), expect_bytes
                )
                self.assertEqual(xattrs.listxattr(path), expect_str)

    def assert_getxattr(self, name_bytes, expect_regular):

        for getxattr, path, expect in [
            (_xattrs.getxattr, self.temp_path_bytes, expect_regular),
            (_xattrs.getxattr, self.temp_symlink, expect_regular),
            (_xattrs.lgetxattr, self.temp_symlink, b''),
            (_xattrs.fgetxattr, self.temp_fd, expect_regular),
        ]:
            with self.subTest((getxattr, path, expect)):
                buffer = ctypes.create_string_buffer(len(expect) + 10)
                if expect:
                    self.assertEqual(
                        getxattr(path, name_bytes, buffer, len(buffer)),
                        len(expect),
                    )
                    self.assertEqual(buffer.raw[:len(expect)], expect)
                else:
                    with self.assertRaises(OSError) as cm:
                        getxattr(path, name_bytes, buffer, len(buffer))
                    self.assertEqual(cm.exception.args[0], errno.ENODATA)

        for path in [
            self.temp_path,
            self.temp_path_bytes,
            self.temp_path_str,
            self.temp_fd,
        ]:
            for name in [
                name_bytes,
                name_bytes.decode('ascii'),
            ]:
                with self.subTest((path, name)):
                    attr = xattrs.getxattr(path, name)
                    if expect_regular:
                        self.assertEqual(attr, expect_regular)
                    else:
                        self.assertIsNone(attr)


class XattrsLowLevelTest(XattrsTestBase):

    def test_xattr_path(self):
        self.do_test_xattr(
            _xattrs.setxattr, _xattrs.removexattr, self.temp_path_bytes
        )

    def test_xattr_symlink(self):
        self.do_test_xattr(
            _xattrs.setxattr, _xattrs.removexattr, self.temp_symlink
        )

    def test_fxattr(self):
        self.do_test_xattr(
            _xattrs.fsetxattr, _xattrs.fremovexattr, self.temp_fd
        )

    def do_test_xattr(self, setxattr, removexattr, path):
        self.assert_listxattr(b'')
        self.assert_getxattr(b'user.foo.bar', b'')
        self.assert_getxattr(b'user.spam', b'')

        self.assertEqual(setxattr(path, b'user.foo.bar', b'x', 1, 0), 0)
        self.assert_listxattr(b'user.foo.bar\x00')
        self.assert_getxattr(b'user.foo.bar', b'x')
        self.assert_getxattr(b'user.spam', b'')

        self.assertEqual(setxattr(path, b'user.spam', b'egg', 3, 0), 0)
        self.assert_listxattr(b'user.foo.bar\x00user.spam\x00')
        self.assert_getxattr(b'user.foo.bar', b'x')
        self.assert_getxattr(b'user.spam', b'egg')

        self.assertEqual(removexattr(path, b'user.foo.bar'), 0)
        self.assert_listxattr(b'user.spam\x00')
        self.assert_getxattr(b'user.foo.bar', b'')
        self.assert_getxattr(b'user.spam', b'egg')

    def test_lxattr(self):
        with self.assertRaises(OSError) as cm:
            _xattrs.lsetxattr(self.temp_symlink, b'user.foo.bar', b'x', 1, 0)
        self.assertEqual(cm.exception.args[0], errno.EPERM)

    def test_setxattr_flags(self):
        name = b'user.foo.bar'

        with self.assertRaises(OSError) as cm:
            _xattrs.setxattr(
                self.temp_path_bytes, name, b'x', 1, _xattrs.XATTR_REPLACE
            )
        self.assertEqual(cm.exception.args[0], errno.ENODATA)

        _xattrs.setxattr(self.temp_path_bytes, name, b'x', 1, 0)
        with self.assertRaises(OSError) as cm:
            _xattrs.setxattr(
                self.temp_path_bytes, name, b'x', 1, _xattrs.XATTR_CREATE
            )
        self.assertEqual(cm.exception.args[0], errno.EEXIST)

    def test_erange_error(self):
        name = b'user.foo.bar'

        self.assertEqual(
            _xattrs.setxattr(self.temp_path_bytes, name, b'xyz', 3, 0), 0
        )

        buffer = ctypes.create_string_buffer(1)

        def do_test_erange_error(func, *args):
            with self.assertRaises(OSError) as cm:
                func(*args, buffer, len(buffer))
            self.assertEqual(cm.exception.args[0], errno.ERANGE)

        do_test_erange_error(_xattrs.listxattr, self.temp_path_bytes)
        do_test_erange_error(_xattrs.flistxattr, self.temp_fd)

        do_test_erange_error(_xattrs.getxattr, self.temp_path_bytes, name)
        do_test_erange_error(_xattrs.fgetxattr, self.temp_fd, name)


class XattrsTest(XattrsTestBase):

    def test_xattr(self):
        name_str = 'user.foo.bar'
        name_bytes = name_str.encode('ascii')
        names = b'%s\x00' % name_bytes

        def do_test_xattr(path, name):
            self.assert_listxattr(b'')
            self.assert_getxattr(name_bytes, b'')

            xattrs.setxattr(path, name, b'x')
            self.assert_listxattr(names)
            self.assert_getxattr(name_bytes, b'x')

            xattrs.removexattr(path, name)
            self.assert_listxattr(b'')
            self.assert_getxattr(name_bytes, b'')

        for name in [name_str, name_bytes]:
            do_test_xattr(self.temp_path, name)
            do_test_xattr(self.temp_path_bytes, name)
            do_test_xattr(self.temp_path_str, name)
            do_test_xattr(self.temp_fd, name)

    def test_setxattr_flags(self):
        name = 'user.foo.bar'

        with self.assertRaises(OSError) as cm:
            xattrs.setxattr(self.temp_path, name, b'x', xattrs.XATTR_REPLACE)
        self.assertEqual(cm.exception.args[0], errno.ENODATA)

        xattrs.setxattr(self.temp_path, name, b'x', 0)
        with self.assertRaises(OSError) as cm:
            xattrs.setxattr(self.temp_path, name, b'x', xattrs.XATTR_CREATE)
        self.assertEqual(cm.exception.args[0], errno.EEXIST)

    def test_read_bytes(self):
        xattrs.setxattr(self.temp_path, 'user.x', b'hello world', 0)

        with self.assertRaisesRegex(
            ValueError, r'size of listxattr exceeds 4'
        ):
            xattrs._read_bytes(
                'listxattr',
                _xattrs.listxattr,
                (self.temp_path_bytes, ),
                buffer_size=2,
                buffer_size_limit=4,
            )

        with self.assertRaisesRegex(ValueError, r'size of user.x exceeds 8'):
            xattrs._read_bytes(
                'user.x',
                _xattrs.getxattr,
                (self.temp_path_bytes, b'user.x'),
                buffer_size=2,
                buffer_size_limit=8,
            )


if __name__ == '__main__':
    unittest.main()
