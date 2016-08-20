import unittest

from subprocess import call, check_call, check_output

from .fixtures import Fixture


@Fixture.inside_container
class PkgsTest(Fixture):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()

    def test_install_pkgs(self):

        # Ensure rkt is not installed.
        self.assertEqual(1, call(['which', 'rkt']))

        check_call(['python3', '-m', 'ops.pkgs', 'install', 'rkt:1.12.0'])

        output = check_output(['rkt', 'version'])
        self.assertTrue(b'rkt Version: 1.12.0' in output, repr(output))

        output = check_output(['rkt', 'image', 'list'])
        self.assertTrue(
            b'coreos.com/rkt/stage1-coreos:1.12.0' in output, repr(output))


if __name__ == '__main__':
    unittest.main()
