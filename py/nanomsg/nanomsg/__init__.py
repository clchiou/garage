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
        self.buffer = None  # A safety measure when an error raised below.
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
        self.fd = None  # A safety measure when an error raised below.
        if protocol is None == socket_fd is None:
            raise AssertionError('one of protocol and socket_fd must be set')
        if protocol is not None:
            self.fd = _check(_nn.nn_socket(domain, protocol))
        else:
            assert socket_fd is not None
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
        if isinstance(address, str):
            address_bytes = address.encode('ascii')
        else:
            address_bytes = address
        endpoint_id = _check(ep_make(self.fd, address_bytes))
        endpoint = ep_class(self, endpoint_id, address)
        self.endpoints[endpoint_id] = endpoint
        return endpoint

    def bind(self, address):
        return self._make_endpoint(address, BindEndpoint, _nn.nn_bind)

    def connect(self, address):
        return self._make_endpoint(address, ConnectEndpoint, _nn.nn_connect)

    def _tx(self, nn_func, message, size, flags, ensure_size):
        if size is None:
            size = len(message)
        nbytes = nn_func(self.fd, message, size, flags)
        if nbytes == -1:
            if (flags & Flag.NN_DONTWAIT) and _nn.nn_errno() == Error.EAGAIN:
                raise NanomsgEagain
            else:
                _raise_errno()
        if size != NN_MSG and nbytes != size and ensure_size:
            raise AssertionError('expect %d instead %d' % (size, nbytes))
        return nbytes

    def send(self, message, size=None, flags=0):
        if isinstance(message, Message):
            message = message.buffer
            size = NN_MSG
        return self._tx(_nn.nn_send, message, size, flags, True)

    def recv(self, message=None, size=None, flags=0):
        if message is None:
            assert size is None or size == NN_MSG
            buffer = ctypes.c_void_p()
            bufp = ctypes.byref(buffer)
            size = self._tx(_nn.nn_recv, bufp, NN_MSG, flags, False)
            return Message(buffer=buffer, size=size)
        else:
            return self._tx(_nn.nn_recv, message, size, flags, False)


class EndpointBase:

    def __init__(self, socket, endpoint_id, address):
        self.socket = socket
        self.endpoint_id = endpoint_id
        self.address = address

    def __repr__(self):
        return ('<%s socket %r, id %d, address %r>' %
                (self.__class__.__name__,
                 self.socket.fd, self.endpoint_id, self.address))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.shutdown()

    def shutdown(self):
        if self.endpoint_id is None:
            return
        endpoint_id, self.endpoint_id = self.endpoint_id, None
        _check(_nn.nn_shutdown(self.socket.fd, endpoint_id))
        self.socket.endpoints.pop(endpoint_id)


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
