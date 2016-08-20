import unittest

import getpass
from subprocess import call, check_call, check_output


@unittest.skipUnless(getpass.getuser() == 'plumber', 'not in container')
class PkgsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Make sure we are inside a container.
        assert getpass.getuser() == 'plumber'

        # Install the fake systemctl because you can't run systemd in a
        # Docker container (can you?).
        check_call(['sudo', 'cp', '/bin/echo', '/usr/local/bin/systemctl'])

    @classmethod
    def tearDownClass(cls):
        # Uninstall the fake systemctl.
        check_call(['sudo', 'rm', '/usr/local/bin/systemctl'])

    def test_install_pkgs(self):

        # Ensure rkt is not installed.
        self.assertEqual(1, call(['which', 'rkt']))

        for pkg in ('rkt:1.12.0', ):
            check_call(['python3', '-m', 'ops.pkgs', 'install', pkg])

        output = check_output(['rkt', 'version'])
        self.assertTrue(b'rkt Version: 1.12.0' in output, repr(output))

        output = check_output(['rkt', 'image', 'list'])
        self.assertTrue(
            b'coreos.com/rkt/stage1-coreos:1.12.0' in output, repr(output))


if __name__ == '__main__':
    unittest.main()
