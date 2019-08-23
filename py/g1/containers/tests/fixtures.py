import unittest

import contextlib
import subprocess
import tempfile
from pathlib import Path

from g1.containers import bases


class TestCaseBase(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.test_repo_tempdir = tempfile.TemporaryDirectory()
        self.test_repo_path = Path(self.test_repo_tempdir.name)
        bases.PARAMS.repository.unsafe_set(self.test_repo_tempdir.name)
        bases.PARAMS.use_root_privilege.unsafe_set(False)

    def tearDown(self):
        self.test_repo_tempdir.cleanup()
        super().tearDown()

    @staticmethod
    def check_shared(path):
        return _check_flock(path, '--shared')

    @staticmethod
    def check_exclusive(path):
        return _check_flock(path, '--exclusive')

    @staticmethod
    def using_shared(path):
        return _using_flock(path, '--shared')

    @staticmethod
    def using_exclusive(path):
        return _using_flock(path, '--exclusive')

    @staticmethod
    def list_dir(path):
        return sorted(p.name for p in path.iterdir())


def _check_flock(path, mode):
    result = subprocess.run(['flock', '--nonblock', mode, str(path), 'true'])
    if result.returncode == 0:
        return True
    elif result.returncode == 1:
        return False
    else:
        raise subprocess.CalledProcessError(result.returncode, result.args)


@contextlib.contextmanager
def _using_flock(path, mode):
    cmd = ['flock', '--nonblock', mode, str(path), 'bash', '-c', 'read']
    with subprocess.Popen(cmd, stdin=subprocess.PIPE) as proc:
        try:
            proc.wait(0.01)  # Wait for ``flock`` to start up.
        except subprocess.TimeoutExpired:
            pass
        else:
            raise subprocess.CalledProcessError(proc.poll(), proc.args)
        try:
            yield
        except:
            proc.kill()
            raise
        else:
            proc.stdin.write(b'\n')
            proc.stdin.flush()
            proc.wait()
            returncode = proc.poll()
            if returncode:
                raise subprocess.CalledProcessError(returncode, proc.args)
