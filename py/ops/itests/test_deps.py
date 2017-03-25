import unittest

from subprocess import call, check_call, check_output

from .fixtures import Fixture


@Fixture.inside_container
class DepsTest(Fixture, unittest.TestCase):

    def test_install_deps(self):
        # Ensure rkt is not installed
        self.assertEqual(1, call(['which', 'rkt']))

        check_call('python3 -m ops --verbose deps install rkt:1.25.0'.split())

        output = check_output(['rkt', 'version'])
        self.assertTrue(b'rkt Version: 1.25.0' in output, repr(output))


if __name__ == '__main__':
    unittest.main()
