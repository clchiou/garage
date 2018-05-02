import unittest

from subprocess import call, check_call, check_output
import os.path

from .fixtures import Fixture


@Fixture.inside_container
class DepsTest(Fixture, unittest.TestCase):

    def test_install_deps(self):
        # Ensure rkt is not installed
        self.assertEqual(1, call(['which', 'rkt']))

        # The current latest version is 1.30.0
        cmd = ('python3 -m itests.ops_runner --verbose deps install rkt:latest'
               .split())
        # Save test time if we have a local tarball
        if os.path.exists('/tmp/tarballs/rkt-v1.30.0.tar.gz'):
            cmd.extend(['--tarball', '/tmp/tarballs/rkt-v1.30.0.tar.gz'])
        check_call(cmd)

        output = check_output(['rkt', 'version'])
        self.assertTrue(b'rkt Version: 1.30.0' in output, repr(output))

        output = check_output(['rkt', 'image', 'list'])
        self.assertTrue(
            b'coreos.com/rkt/stage1-coreos:1.30.0' in output,
            repr(output),
        )


if __name__ == '__main__':
    unittest.main()
