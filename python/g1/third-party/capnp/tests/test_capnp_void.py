import unittest

import capnp

try:
    from capnp import _capnp_test
except ImportError:
    _capnp_test = None

# pylint: disable=c-extension-no-member


@unittest.skipUnless(_capnp_test, '_capnp_test unavailable')
class VoidTest(unittest.TestCase):

    def test_void_type(self):
        # ``VoidType`` is not declared as subclass of ``type`` for now.
        self.assertFalse(issubclass(capnp.VoidType, type))

    def test_void_object_singleton(self):
        self.assertIs(capnp.VOID, capnp.VoidType())

    def test_void(self):
        self.assertIs(capnp.VOID, _capnp_test.takeVoid(capnp.VOID))
        self.assertFalse(bool(capnp.VOID))


if __name__ == '__main__':
    unittest.main()
