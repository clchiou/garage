import unittest

import getpass
from subprocess import call, check_call, check_output


class PkgsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Make sure we are inside a container.
        assert getpass.getuser() == 'plumber'

    def test_install_pkgs(self):

        # Ensure rkt and docker2aci are not installed.
        self.assertEqual(1, call(['which', 'rkt']))
        self.assertEqual(1, call(['which', 'docker2aci']))

        for pkg in ('rkt:1.6.0', 'docker2aci:0.9.3'):
            check_call(['python3', '-m', 'ops.pkgs', 'install', pkg])

        output = check_output(['rkt', 'version'])
        self.assertTrue(b'rkt Version: 1.6.0' in output, repr(output))

        output = check_output(['rkt', 'image', 'list'])
        self.assertTrue(
            b'coreos.com/rkt/stage1-coreos:1.6.0' in output, repr(output))

        output = check_output(['docker2aci', '-version'])
        self.assertTrue(b'docker2aci version v0.9.3' in output, repr(output))


if __name__ == '__main__':
    unittest.main()
