import unittest

from garage import parameters


class ParametersTest(unittest.TestCase):

    def test_parameter_namespace(self):

        ns = parameters.ParameterNamespace()

        pattern = r'expect .*-typed value instead of 1'
        with self.assertRaisesRegex(AssertionError, pattern):
            ns['x'] = 1

        nns = parameters.Namespace(ns)

        ns1 = parameters.ParameterNamespace()
        ns2 = parameters.ParameterNamespace()
        ns['ns1'] = ns1
        nns.ns2 = ns2
        self.assertEqual({'ns1': ns1, 'ns2': ns2}, dict(ns.items()))

        pattern = r'parameter is not found: xyz'
        with self.assertRaisesRegex(AttributeError, pattern):
            nns.xyz

        # Forbid overriding values.
        pattern = r"expect 'ns2' not in"
        with self.assertRaisesRegex(AssertionError, pattern):
            nns.ns2 = ns2

        pattern = r"expect parameter name not start with underscore: '_x'"
        with self.assertRaisesRegex(AssertionError, pattern):
            nns._x = ns1

    def test_parameter(self):

        bp = parameters.define(False)

        bp.set(True)
        self.assertTrue(bp.get())

        # Forbid write-after-read.
        with self.assertRaises(AssertionError):
            bp.set(False)

        bp.unsafe_set(False)
        self.assertFalse(bp.get())

        pattern = r'expect .*-typed value instead of 1'
        with self.assertRaisesRegex(AssertionError, pattern):
            bp.unsafe_set(1)


if __name__ == '__main__':
    unittest.main()
