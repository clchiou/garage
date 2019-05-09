import unittest

from capnp import _capnp  # pylint: disable=unused-import

try:
    from capnp import _capnp_test
except ImportError:
    _capnp_test = None

# pylint: disable=c-extension-no-member


@unittest.skipUnless(_capnp_test, '_capnp_test unavailable')
class MessageTest(unittest.TestCase):

    def test_reader(self):
        data = b''
        r = _capnp.FlatArrayMessageReader(data)
        self.assertFalse(r.isCanonical())

    def test_builder(self):
        b = _capnp.MallocMessageBuilder()
        self.assertTrue(b.isCanonical())
        self.assertEqual(_capnp.computeSerializedSizeInWords(b), 2)
        self.assertEqual(len(_capnp.messageToFlatArray(b).asBytes()), 16)
        array = _capnp.messageToPackedArray(b)
        self.assertEqual(_capnp.computeUnpackedSizeInWords(array.asBytes()), 2)
        self.assertEqual(array.asBytes(), b'\x10\x01\x00\x00')


if __name__ == '__main__':
    unittest.main()
