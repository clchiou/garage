__all__ = [
    'NanomsgError',
    'NanomsgEagain',
    'Message',
    'Socket',
    'BindEndpoint',
    'ConnectEndpoint',
    'device',
    'terminate',
    # Extend with constants.__all__
]

import ctypes
from collections import OrderedDict

from . import _nanomsg as _nn
from . import constants
from .constants import *


__all__.extend(constants.__all__)


class NanomsgError(Exception):
    pass


class NanomsgEagain(Exception):
    pass


def _check(ret):
    if ret == -1:
        _raise_errno()
    return ret


def _raise_errno():
    raise NanomsgError(_nn.nn_strerror(_nn.nn_errno()).decode('ascii'))


class Message:

    def __init__(self, size, allocation_type=0, *, buffer=None):
        if buffer:
            self.buffer = buffer
        else:
            self.buffer = _nn.nn_allocmsg(size, allocation_type)
            if self.buffer is None:
                _raise_errno()
        self.size = size

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.free()

    def __del__(self):
        # Don't call super's __del__ since `object` doesn't have one.
        self.free()

    def resize(self, size):
        self.buffer = _nn.nn_reallocmsg(self.buffer, size)
        if self.buffer is None:
            _raise_errno()
        self.size = size

    def free(self):
        if self.buffer is None:
            return
        buffer, self.buffer = self.buffer, None
        _check(_nn.nn_freemsg(buffer))


class Socket:

    def __init__(self, *, domain=Domain.AF_SP, protocol=None, socket_fd=None):
        if protocol is not None and socket_fd is not None:
            raise AssertionError('both protocol and socket_fd are set')
        if protocol is not None:
            self.fd = _check(_nn.nn_socket(domain, protocol))
        else:
            self.fd = socket_fd
        self.endpoints = OrderedDict()

    def __repr__(self):
        binds = []
        connects = []
        for endpoint in self.endpoints.values():
            if isinstance(endpoint, BindEndpoint):
                binds.append(endpoint.address)
            elif isinstance(endpoint, ConnectEndpoint):
                connects.append(endpoint.address)
            else:
                raise AssertionError(repr(endpoint))
        return ('<%s fd %r, listen on %r, connect to %r>' %
                (self.__class__.__name__, self.fd, binds, connects))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        # Don't call super's __del__ since `object` doesn't have one.
        self.close()

    def close(self):
        if self.fd is None:
            return
        fd, self.fd = self.fd, None
        self.endpoints.clear()
        _check(_nn.nn_close(fd))

    def _make_endpoint(self, address, ep_class, ep_make):
        if self.fd is None:
            raise AssertionError
        endpoint_id = _check(ep_make(self.fd, address))
        endpoint = ep_class(self, endpoint_id, address)
        self.endpoints[endpoint_id] = endpoint
        return endpoint

    def bind(self, address):
        return self._make_endpoint(address, BindEndpoint, _nn.nn_bind)

    def connect(self, address):
        return self._make_endpoint(address, ConnectEndpoint, _nn.nn_connect)

    def _tx(self, nn_func, message, count, flags):
        if count is None:
            count = len(message)
        nbytes = nn_func(self.fd, message, count, flags)
        if nbytes == -1:
            if (flags & Flag.NN_DONTWAIT) and _nn.nn_errno() == Error.EAGAIN:
                raise NanomsgEagain
            else:
                _raise_errno()
        if count != NN_MSG and nbytes != count:
            raise AssertionError('expect %d instead %d' % (count, nbytes))
        return nbytes

    def send(self, message, count=None, flags=0):
        if isinstance(message, Message):
            message = message.buffer
            count = NN_MSG
        self._tx(_nn.nn_send, message, count, flags)

    def recv(self, message=None, count=None, flags=0):
        if message is None:
            buffer = ctypes.c_void_p()
            message = ctypes.byref(buffer)
            count = NN_MSG
        nbytes = self._tx(_nn.nn_recv, message, count, flags)
        if count == NN_MSG:
            message = Message(buffer=buffer, size=nbytes)
        return message


class EndpointBase:

    def __init__(self, socket, endpoint_id, address):
        self.socket = socket
        self.endpoint_id = endpoint_id
        self.address = address

    def __repr__(self):
        return ('<%s socket %r, id %d, address %r>' %
                (self.__class__.__name__,
                 self.socket.fd, self.endpoint_id, self.address))

    def shutdown(self):
        _check(_nn.nn_shutdown(self.socket.fd, self.endpoint_id))
        self.socket.endpoints.pop(self.endpoint_id)


class BindEndpoint(EndpointBase):
    pass


class ConnectEndpoint(EndpointBase):
    pass


def device(sock1, sock2=None):
    fd1 = sock1.fd
    fd2 = sock2.fd if sock2 is not None else -1
    _check(_nn.nn_device(fd1, fd2))


def terminate():
    _nn.nn_term()
