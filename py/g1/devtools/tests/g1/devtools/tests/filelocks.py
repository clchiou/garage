__all__ = [
    'Fixture',
]

import contextlib
import subprocess


class Fixture:

    @staticmethod
    def check_shared(path):
        return _check_file_lock(path, '--shared')

    @staticmethod
    def check_exclusive(path):
        return _check_file_lock(path, '--exclusive')

    @staticmethod
    def using_shared(path):
        return _using_file_lock(path, '--shared')

    @staticmethod
    def using_exclusive(path):
        return _using_file_lock(path, '--exclusive')


def _check_file_lock(path, mode):
    result = subprocess.run(['flock', '--nonblock', mode, str(path), 'true'])
    if result.returncode == 0:
        return True
    elif result.returncode == 1:
        return False
    else:
        raise subprocess.CalledProcessError(result.returncode, result.args)


@contextlib.contextmanager
def _using_file_lock(path, mode):
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
