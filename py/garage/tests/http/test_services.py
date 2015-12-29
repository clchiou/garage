import unittest

from garage.http.services import Version


class VersionTest(unittest.TestCase):

    def test_parse(self):
        self.assertTupleEqual((0, 0, 0), Version.parse('0.0.0'))
        self.assertTupleEqual((0, 0, 0), Version.parse('000.000.000'))
        self.assertTupleEqual((1, 2, 3), Version.parse('001.002.003'))
        with self.assertRaises(ValueError):
            Version.parse('0.0.c')
        with self.assertRaises(ValueError):
            Version.parse('1.2')
        with self.assertRaises(ValueError):
            Version.parse('1.')

    def test_str(self):
        self.assertEqual('0.0.0', str(Version(0, 0, 0)))
        self.assertEqual('1.2.3', str(Version(1, 2, 3)))

    def test_is_compatible_with(self):
        v0_1_0 = Version.parse('0.1.0')
        v0_2_0 = Version.parse('0.2.0')
        v1_0_0 = Version.parse('1.0.0')

        self.assertTrue(v0_1_0.is_compatible_with(v0_2_0))
        self.assertTrue(v0_2_0.is_compatible_with(v0_1_0))

        self.assertFalse(v0_1_0.is_compatible_with(v1_0_0))
        self.assertFalse(v1_0_0.is_compatible_with(v0_1_0))

    def test_newer(self):
        versions = [
            Version.parse('0.1.0'),
            Version.parse('0.1.1'),
            Version.parse('0.2.0'),
            Version.parse('0.10.0'),
            Version.parse('1.0.0'),
        ]
        for v0, v1 in zip(versions, versions[1:]):
            self.assertGreater(v1, v0)
