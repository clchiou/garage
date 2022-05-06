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
class ResourceTypesTest(unittest.TestCase):

    def test_throwing_dtor(self):
        resource = _capnp_test.ThrowingDtorResource()
        with self.assertRaisesRegex(
            RuntimeError,
            r'failed: Test ThrowingDtorResource',
        ):
            resource._reset()

    def test_throwing_dtor_when_another_exc_active(self):
        buffer_outer = io.StringIO()
        buffer_inner = io.StringIO()
        with contextlib.redirect_stderr(buffer_outer):
            with self.assertRaisesRegex(Exception, r'some error'):
                try:
                    raise Exception('some error')
                finally:
                    with contextlib.redirect_stderr(buffer_inner):
                        _capnp_test.ThrowingDtorResource()
                        gc.collect()
        self.assertEqual(buffer_outer.getvalue(), '')
        log = buffer_inner.getvalue()
        self.assertRegex(log, r'Test ThrowingDtorResource')
        self.assertNotRegex(
            log,
            r'During handling of the above exception, '
            r'another exception occurred',
        )

    def test_error_indicator(self):
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            with self.assertRaisesRegex(RuntimeError, r'Test error indicator'):
                _capnp_test.testErrorIndicator()
        self.assertRegex(buffer.getvalue(), r'Test ThrowingDtorResource')

    def test_returning_resource(self):
        self.assertEqual(_capnp_test.DummyResource.numCtor, 0)
        self.assertEqual(_capnp_test.DummyResource.numMove, 0)
        self.assertEqual(_capnp_test.DummyResource.numDtor, 0)
        _capnp_test.DummyResourceFactory().make()._reset()
        self.assertEqual(_capnp_test.DummyResource.numCtor, 1)
        # DummyResource is not moved at all; this is probably a result
        # of compiler optimization.
        self.assertEqual(_capnp_test.DummyResource.numMove, 0)
        self.assertEqual(_capnp_test.DummyResource.numDtor, 1)


if __name__ == '__main__':
    unittest.main()
