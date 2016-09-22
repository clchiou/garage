import unittest

from subprocess import call, check_call, check_output

from .fixtures import Fixture


@Fixture.inside_container
class DepsTest(Fixture):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()

    def test_install_deps(self):

        # Ensure rkt is not installed.
        self.assertEqual(1, call(['which', 'rkt']))

        check_call([
            'python3', '-m', 'ops', 'deps', 'install', '--verbose', 'rkt:1.12.0',
            # SHA-512 checksum of the package.
            '7fdbb523083a0162fb3d5be6c8bdc6ed65a6e580aa635465a056d4f3a8a3b88f9e46d072a241df4c6ce3374bbc0bc7b143928c5b8f93ef1878da15227d339cc0',
        ])

        output = check_output(['rkt', 'version'])
        self.assertTrue(b'rkt Version: 1.12.0' in output, repr(output))

        output = check_output(['rkt', 'image', 'list'])
        self.assertTrue(
            b'coreos.com/rkt/stage1-coreos:1.12.0' in output, repr(output))


if __name__ == '__main__':
    unittest.main()
