__all__ = [
    'Connector',
]

import contextlib
import logging
import pickle
from multiprocessing.connection import Client


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


class Connector:

    def __init__(self, address, protocol, authkey):
        self.address = address
        self.protocol = protocol
        self.authkey = bytes(authkey, encoding='ascii')

    @contextlib.contextmanager
    def connect(self):
        with Client(self.address, authkey=self.authkey) as conn:
            version_info = conn.recv()['version_info']
            LOG.info('server version %s', version_info)
            server = ServerStub(conn, self.address, self.protocol)
            try:
                yield server
            finally:
                err = server.close()
                if err:
                    LOG.error('cannot close stub due to %s', err)

    def shutdown(self):
        with self.connect() as server:
            err = server.shutdown()
            if err:
                LOG.error('cannot shutdown server due to %s', err)


class ServerStub:

    def __init__(self, conn, address, protocol):
        self.stub = Stub(conn, address, protocol)
        self.server_vars = Vars(self.stub, 'server_')
        self.vars = Vars(self.stub)
        self._closed = False

    def shutdown(self):
        if self._closed:
            return False
        _, err = self.stub({'command': 'shutdown'})
        if not err:
            self._closed = True
        return err

    def close(self):
        if self._closed:
            return False
        _, err = self.stub({'command': 'close'})
        if not err:
            self._closed = True
        return err

    def execute(self, source):
        _, err = self.stub({
            'command': 'execute',
            'source': source,
            'filename': self.stub.address,
        })
        return err


class Vars:

    def __init__(self, stub, prefix=''):
        object.__setattr__(self, '_stub', stub)
        object.__setattr__(self, '_prefix', prefix)

    def __getattr__(self, name):
        response, err = self._stub(
            {'command': self._prefix + 'get', 'name': name})
        assert ('value' in response) != bool(err)
        if err:
            raise AttributeError('cannot get %r due to %s' % (name, err))
        return response.get('value')

    def __setattr__(self, name, value):
        _, err = self._stub(
            {'command': self._prefix + 'set', 'name': name, 'value': value})
        if err:
            raise AttributeError('cannot set %r due to %s' % (name, err))

    def __delattr__(self, name):
        _, err = self._stub(
            {'command': self._prefix + 'del', 'name': name})
        if err:
            raise AttributeError('cannot delete %r due to %s' % (name, err))


class Stub:

    def __init__(self, conn, address, protocol):
        self.conn = conn
        self.address = address
        self.protocol = protocol

    def __call__(self, request):
        self.conn.send_bytes(pickle.dumps(request, protocol=self.protocol))
        response = self.conn.recv()
        return response, response.get('error')
