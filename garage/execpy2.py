"""Execute Python2 codes."""

__all__ = [
    'python2',
]

import contextlib
import logging
import os.path
import pickle
import random
import shutil
import subprocess
import tempfile
import time
from multiprocessing.connection import Client

import garage.execserver
from garage.app import D


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


@contextlib.contextmanager
def python2(executable='python2'):
    authkey = str(random.randint(1, 1e8))
    with create_server_path() as address, \
            start_server(executable, address, authkey), \
            create_client(address, authkey) as conn:
        version_info = conn.recv()['version_info']
        LOG.info('server version %s', version_info)
        if version_info[0] != 2:
            raise Exception(
                '%s is not at version 2: %r' % (executable, version_info))
        server = Server(conn, address)
        try:
            server.set_wait()
            yield server
        finally:
            server.shutdown()


@contextlib.contextmanager
def create_server_path():
    tempdir = tempfile.mkdtemp()
    try:
        server_path = tempfile.mktemp(dir=tempdir)
        LOG.info('server path %s', server_path)
        yield server_path
    finally:
        shutil.rmtree(tempdir)


@contextlib.contextmanager
def start_server(python, address, authkey):
    script_path = garage.execserver.__file__
    args = [python, script_path, '--server-path', address]
    if D['VERBOSE'] > 0:
        args.append('-' + 'v' * D['VERBOSE'])
    server_proc = subprocess.Popen(args, env={'AUTHKEY': authkey})
    try:
        yield server_proc
    finally:
        if server_proc.wait() != 0:
            LOG.warning('server returns %d', server_proc.returncode)


def create_client(address, authkey):
    wait_file_creation(address, timeout=3)
    authkey_bytes = bytes(authkey, encoding='ascii')
    return Client(address, authkey=authkey_bytes)


def wait_file_creation(path, timeout):
    end_time = time.time() + timeout
    while not os.path.exists(path):
        time.sleep(0.1)
        if end_time < time.time():
            raise Exception('timeout')


class Server:

    def __init__(self, conn, filename):
        self.conn = conn
        self.filename = filename

    def call(self, request):
        self.conn.send_bytes(pickle.dumps(request, protocol=2))
        response = self.conn.recv()
        return response.get('success'), response

    def shutdown(self):
        success, response = self.call({'command': 'shutdown'})
        if not success:
            LOG.error('cannot shutdown: %s', response['reason'])

    def set_wait(self, value=True):
        success, response = self.call({
            'command': 'set-wait',
            'value': value,
        })
        if not success:
            LOG.error('cannot set-wait: %s', response['reason'])
        return success

    def get(self, name):
        success, response = self.call({
            'command': 'get',
            'name': name,
        })
        if not success:
            raise NameError('name \'%s\' cannot be read' % name)
        return response['value']

    def set(self, name, value):
        success, response = self.call({
            'command': 'get',
            'name': name,
            'value': value,
        })
        if not success:
            LOG.error('cannot set \'%s\': %s', name, response['reason'])
        return success

    def execute(self, source):
        success, response = self.call({
            'command': 'execute',
            'source': source,
            'filename': self.filename,
        })
        if not success:
            LOG.error('cannot execute code: %s', response['reason'])
        return success
