__all__ = [
    'python',
]

import contextlib
import logging
import os
import os.path
import random
import shutil
import subprocess
import tempfile
import time

import garage.multiprocessing.server
from garage.multiprocessing.client import Connector


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


@contextlib.contextmanager
def python(executable='python2', protocol=2, authkey=None):
    """Start a server and return a Connector object
       (default to python2).
    """
    authkey = authkey or str(random.randint(1, 1e8))
    with create_socket() as addr, start_server(executable, addr, authkey):
        connector = Connector(addr, protocol, authkey)
        try:
            yield connector
        finally:
            connector.shutdown()


@contextlib.contextmanager
def create_socket():
    tempdir = tempfile.mkdtemp()
    try:
        socket_path = tempfile.mktemp(dir=tempdir)
        LOG.info('socket path %s', socket_path)
        yield socket_path
    finally:
        shutil.rmtree(tempdir)


@contextlib.contextmanager
def start_server(executable, address, authkey):
    script_path = garage.multiprocessing.server.__file__
    args = [executable, script_path, '--listen-sock', address]
    if LOG.isEnabledFor(logging.INFO):
        args.append('-v')
    env = dict(os.environ)
    env['AUTHKEY'] = authkey
    server_proc = subprocess.Popen(args, env=env)
    try:
        wait_file_creation(address, timeout=3)
        yield server_proc
    finally:
        if server_proc.wait() != 0:
            LOG.warning('server returns %d', server_proc.returncode)


def wait_file_creation(path, timeout):
    end_time = time.time() + timeout
    while not os.path.exists(path):
        time.sleep(0.1)
        if end_time < time.time():
            raise Exception('timeout')
