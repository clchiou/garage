__all__ = [
    'RpcConnectionError',
    'RpcError',

    'Connector',
]

import contextlib
import functools
import logging
import pickle
from multiprocessing.connection import Client

from garage import asserts


LOG = logging.getLogger(__name__)


class RpcError(Exception):
    pass


class RpcConnectionError(RpcError):
    pass


class Connector:

    def __init__(self, address, protocol, authkey):
        self.address = address
        self.protocol = protocol
        self.authkey = bytes(authkey, encoding='ascii')

    @contextlib.contextmanager
    def connect(self):
        try:
            with Client(self.address, authkey=self.authkey) as conn:
                version_info = conn.recv()['version_info']
                LOG.debug('server version %s', version_info)
                server = ServerStub(conn, self.address, self.protocol)
                try:
                    yield server
                finally:
                    server.close()
        except (FileNotFoundError, EOFError) as exc:
            raise RpcConnectionError(
                'cannot connect to %s' % self.address) from exc

    def shutdown(self):
        # close/shutdown should never fail (i.e., no-throw).
        try:
            with self.connect() as server:
                server.shutdown()
        except (ConnectionResetError, RpcConnectionError):
            LOG.warning('cannot shutdown server', exc_info=True)


class ServerStub:

    def __init__(self, conn, address, protocol):
        self.stub = Stub(conn, address, protocol)
        self.vars = Vars(self.stub)
        self.funcs = Funcs(self.stub)
        # Don't call close/shutdown if it has been closed.  Although
        # this doesn't make the program "more right", it keeps logs
        # cleaner.
        self._closed = False

    def shutdown(self):
        # close/shutdown should never fail (i.e., no-throw).
        if self._closed:
            return False
        try:
            _, err = self.stub({'command': 'shutdown'})
            if err:
                LOG.error('cannot shutdown server due to %s', err)
        except RpcError as exc:
            LOG.warning('cannot send shutdown request', exc_info=True)
            err = exc
        if not err:
            self._closed = True
        return err

    def close(self):
        # close/shutdown should never fail (i.e., no-throw).
        if self._closed:
            return False
        try:
            _, err = self.stub({'command': 'close'})
            if err:
                LOG.error('cannot close stub due to %s', err)
        except RpcError as exc:
            LOG.warning('cannot send close request', exc_info=True)
            err = exc
        if not err:
            self._closed = True
        return err

    def execute(self, source):
        _, err = self.stub({
            'command': 'execute',
            'source': source,
            'filename': self.stub.address,
        })
        if err:
            raise RpcError('cannot execute %r due to %s' % (source, err))


class Vars:

    def __init__(self, stub):
        object.__setattr__(self, '_stub', stub)

    def __getattr__(self, name):
        response, err = self._stub({'command': 'get', 'name': name})
        asserts.postcond(
            ('value' in response) != bool(err),
            'expect either %r or %r but not both', response, err)
        if err:
            raise AttributeError('cannot get %r due to %s' % (name, err))
        return response.get('value')

    def __setattr__(self, name, value):
        _, err = self._stub({'command': 'set', 'name': name, 'value': value})
        if err:
            raise AttributeError('cannot set %r due to %s' % (name, err))

    def __delattr__(self, name):
        _, err = self._stub({'command': 'del', 'name': name})
        if err:
            raise AttributeError('cannot delete %r due to %s' % (name, err))


class Funcs:

    def __init__(self, stub):
        self._stub = stub

    def __getattr__(self, name):
        return functools.partial(self._call_stub, name)

    def _call_stub(self, name, *args, **kwargs):
        response, err = self._stub(
            {'command': 'call', 'name': name, 'args': args, 'kwargs': kwargs})
        asserts.postcond(
            ('value' in response) != bool(err),
            'expect either %r or %r but not both', response, err)
        if err:
            raise RpcError('cannot call %r due to %s' % (name, err))
        return response.get('value')


class Stub:

    def __init__(self, conn, address, protocol):
        self.conn = conn
        self.address = address
        self.protocol = protocol

    def __call__(self, request):
        try:
            self.conn.send_bytes(pickle.dumps(request, protocol=self.protocol))
            response = self.conn.recv()
        except IOError as exc:
            raise RpcError('cannot send request %r' % request) from exc
        return response, response.get('error')
