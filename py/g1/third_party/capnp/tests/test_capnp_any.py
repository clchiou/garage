import unittest

from capnp import _capnp  # pylint: disable=unused-import

try:
    from capnp import _capnp_test
except ImportError:
    _capnp_test = None

# pylint: disable=c-extension-no-member


@unittest.skipUnless(_capnp_test, '_capnp_test unavailable')
class AnyTypeTest(unittest.TestCase):

    def test_qualname(self):
        for qualname in (
            'AnyList',
            'AnyList.Reader',
            'AnyList.Builder',
            'AnyStruct',
            'AnyStruct.Reader',
            'AnyStruct.Builder',
            'AnyPointer',
            'AnyPointer.Reader',
            'AnyPointer.Builder',
        ):
            with self.subTest(qualname):
                obj_type = _capnp
                for path in qualname.split('.'):
                    obj_type = getattr(obj_type, path)
                self.assertEqual(obj_type.__qualname__, qualname)

    def test_any_list(self):
        r = _capnp.AnyList.Reader()
        self.assertEqual(r.getElementSize(), _capnp.ElementSize.VOID)
        self.assertEqual(r.size(), 0)
        self.assertEqual(r.getRawBytes(), b'')
        self.assertEqual(r, r)
        self.assertEqual(r, _capnp.AnyList.Reader())
        size = r.totalSize()
        self.assertEqual(size.wordCount, 0)
        self.assertEqual(size.capCount, 0)

    def test_any_struct(self):
        r = _capnp.AnyStruct.Reader()
        size = r.totalSize()
        self.assertEqual(size.wordCount, 0)
        self.assertEqual(size.capCount, 0)
        self.assertEqual(r.getDataSection(), b'')
        self.assertEqual(len(r.canonicalize()), 1)
        self.assertEqual(r, r)
        self.assertEqual(r, _capnp.AnyStruct.Reader())

    def test_any_pointer(self):
        r = _capnp.AnyPointer.Reader()
        size = r.targetSize()
        self.assertEqual(size.wordCount, 0)
        self.assertEqual(size.capCount, 0)
        self.assertEqual(r.getPointerType(), _capnp.PointerType.NULL_)
        self.assertTrue(r.isNull())
        self.assertFalse(r.isStruct())
        self.assertFalse(r.isList())
        self.assertFalse(r.isCapability())
        self.assertEqual(r, r)
        self.assertEqual(r, _capnp.AnyPointer.Reader())


if __name__ == '__main__':
    unittest.main()
