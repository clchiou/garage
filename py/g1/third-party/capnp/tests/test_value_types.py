import unittest

import contextlib
import gc
import io

from capnp import _capnp  # pylint: disable=unused-import

try:
    from capnp import _capnp_test
except ImportError:
    _capnp_test = None

# pylint: disable=c-extension-no-member


@unittest.skipUnless(_capnp_test, '_capnp_test unavailable')
class ValueTypesTest(unittest.TestCase):

    def test_throwing_dtor(self):
        self.assertEqual(_capnp_test.ThrowingDtorValue.numCtor, 0)
        self.assertEqual(_capnp_test.ThrowingDtorValue.numCopy, 0)
        self.assertEqual(_capnp_test.ThrowingDtorValue.numMove, 0)
        self.assertEqual(_capnp_test.ThrowingDtorValue.numDtor, 0)

        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            _capnp_test.ThrowingDtorValue()
            gc.collect()
        self.assertRegex(buffer.getvalue(), r'Test dtor throw')

        self.assertEqual(_capnp_test.ThrowingDtorValue.numCtor, 1)
        # It is important that ``ThrowingDtorValue`` is not copied in
        # this unit test; otherwise, the original object might not be
        # held by a ``ValueHolder`` object.  Then what do do when its
        # destructor is throwing?  Process aborts?  (But we can't simply
        # KJ_DISALLOW_COPY(ThrowingDtorValue) because compiler still
        # needs copy ctor somehow).
        self.assertEqual(_capnp_test.ThrowingDtorValue.numCopy, 0)
        self.assertEqual(_capnp_test.ThrowingDtorValue.numMove, 1)
        self.assertEqual(_capnp_test.ThrowingDtorValue.numDtor, 2)


if __name__ == '__main__':
    unittest.main()
