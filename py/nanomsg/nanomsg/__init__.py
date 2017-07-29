__all__ = [
    'Message',
    'Socket',
    'BindEndpoint',
    'ConnectEndpoint',
    'device',
    'terminate',
    # Extend with constants and errors.
]

import ctypes
from collections import OrderedDict
from functools import partial

from . import _nanomsg as _nn
from . import constants
from . import errors

from .constants import *
from .errors import *


__all__.extend(constants.__all__)
__all__.extend(errors.__all__)

if len(set(__all__)) != len(__all__):
    raise AssertionError('names conflict: %r' % __all__)


_PyBUF_READ = 0x100
_PyBUF_WRITE = 0x200

_PyMemoryView_FromMemory = ctypes.pythonapi.PyMemoryView_FromMemory
_PyMemoryView_FromMemory.argtypes = [
    ctypes.c_void_p,
    ctypes.c_ssize_t,
    ctypes.c_int,
]
_PyMemoryView_FromMemory.restype = ctypes.py_object


class Message:

    def __init__(self, size, allocation_type=0, *, buffer=None):
        self.buffer = None  # A safety measure when an error raised below.
        if buffer:
            self.buffer = buffer
        else:
            self.buffer = _nn.nn_allocmsg(size, allocation_type)
            if self.buffer is None:
                raise NanomsgError.make(_nn.nn_errno())
        self.size = size

    def __repr__(self):
        return ('<%s addr 0x%016x, size 0x%x>' %
                (self.__class__.__name__, self.buffer.value, self.size))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.free()

    def __del__(self):
        # Don't call super's __del__ since `object` doesn't have one.
        self.free()

    def as_memoryview(self):
        if self.buffer is None:
            raise AssertionError
        return _PyMemoryView_FromMemory(
            self.buffer,
            self.size,
            _PyBUF_READ | _PyBUF_WRITE,
        )

    def resize(self, size):
        if self.buffer is None:
            raise AssertionError
        self.buffer = _nn.nn_reallocmsg(self.buffer, size)
        if self.buffer is None:
            raise NanomsgError.make(_nn.nn_errno())
        self.size = size

    def free(self):
        if self.buffer is None:
            return
        buffer, self.buffer = self.buffer, None
        errors.check(_nn.nn_freemsg(buffer))


class SocketBase:

    def __init__(self, *, domain=AF_SP, protocol=None, socket_fd=None):
        # Set fd to None as a safety measure in case subclass's __init__
        # raises exception since __del__ need at least self.fd.
        self.fd = None

        if protocol is None == socket_fd is None:
            raise AssertionError('one of protocol and socket_fd must be set')
        if protocol is not None:
            self.fd = errors.check(_nn.nn_socket(domain, protocol))
        else:
            assert socket_fd is not None
            self.fd = socket_fd

        # Keep a strong reference to endpoint objects to prevent them
        # from being released because users are not expected to keep a
        # reference to these endpoint objects, i.e., users usually treat
        # bind() and connect() as a void function.
        self.endpoints = OrderedDict()

        # Make a separate namespace for some of the options (don't
        # clutter up this namespace).
        self.options = OptionsProxy(self)

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

    ### Manage socket life cycle.

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
        self.endpoints.clear()  # Make __repr__() cleaner.
        errors.check(_nn.nn_close(fd))

    ### Configure this socket.

    def getsockopt(self, level, option, option_size=64):

        if self.fd is None:
            raise AssertionError

        option_type = option.value.type

        if option_type is OptionType.NN_TYPE_INT:
            optval = ctypes.byref(ctypes.c_int())
            optvallen = ctypes.sizeof(ctypes.c_int)

        elif option_type is OptionType.NN_TYPE_STR:
            optval = ctypes.create_string_buffer(option_size)
            optvallen = len(optval)

        else:
            raise AssertionError

        optvallen = ctypes.byref(ctypes.c_size_t(optvallen))

        errors.check(_nn.nn_getsockopt(
            self.fd, level, option.value, optval, optvallen))

        if option_type is OptionType.NN_TYPE_INT:
            value = optval._obj.value

        elif option_type is OptionType.NN_TYPE_STR:
            size = optvallen._obj.value
            value = optval.raw[:size].decode('ascii')

        else:
            raise AssertionError

        if option.value.unit is OptionUnit.NN_UNIT_BOOLEAN:
            value = (False, True)[value]

        return value

    def setsockopt(self, level, option, value):

        if self.fd is None:
            raise AssertionError

        option_type = option.value.type

        if isinstance(value, bool):
            if option_type is not OptionType.NN_TYPE_INT:
                raise ValueError('option %s is not int-typed' % option.name)
            optval = ctypes.byref(ctypes.c_int(int(value)))
            optvallen = ctypes.sizeof(ctypes.c_int)

        elif isinstance(value, int):
            if option_type is not OptionType.NN_TYPE_INT:
                raise ValueError('option %s is not int-typed' % option.name)
            optval = ctypes.byref(ctypes.c_int(value))
            optvallen = ctypes.sizeof(ctypes.c_int)

        elif isinstance(value, str):
            if option_type is not OptionType.NN_TYPE_STR:
                raise ValueError('option %s is not str-typed' % option.name)
            optval = value.encode('ascii')
            optvallen = len(optval)

        elif isinstance(value, bytes):
            if option_type is not OptionType.NN_TYPE_STR:
                raise ValueError('option %s is not str-typed' % option.name)
            optval = value
            optvallen = len(optval)

        else:
            raise ValueError('unsupported type: {!r}'.format(value))

        errors.check(_nn.nn_setsockopt(
            self.fd, level, option.value, optval, optvallen))

    ### Add endpoints to this socket.

    def bind(self, address):
        if self.fd is None:
            raise AssertionError
        return self._make_endpoint(address, BindEndpoint, _nn.nn_bind)

    def connect(self, address):
        if self.fd is None:
            raise AssertionError
        return self._make_endpoint(address, ConnectEndpoint, _nn.nn_connect)

    def _make_endpoint(self, address, ep_class, ep_make):
        if isinstance(address, str):
            address_bytes = address.encode('ascii')
        else:
            address_bytes = address
        endpoint_id = errors.check(ep_make(self.fd, address_bytes))
        endpoint = ep_class(self, endpoint_id, address)
        self.endpoints[endpoint_id] = endpoint
        return endpoint

    ### Transmit data.

    def _blocking_send(self, message, size, flags):
        if self.fd is None:
            raise AssertionError
        if isinstance(message, Message):
            message = message.buffer
            size = NN_MSG
        return self._tx(_nn.nn_send, message, size, flags, True)

    def _blocking_recv(self, message, size, flags):
        if self.fd is None:
            raise AssertionError
        if message is None:
            assert size is None or size == NN_MSG
            buffer = ctypes.c_void_p()
            bufp = ctypes.byref(buffer)
            size = self._tx(_nn.nn_recv, bufp, NN_MSG, flags, False)
            return Message(buffer=buffer, size=size)
        else:
            return self._tx(_nn.nn_recv, message, size, flags, False)

    def _tx(self, nn_func, message, size, flags, ensure_size):
        if size is None:
            size = len(message)
        nbytes = errors.check(nn_func(self.fd, message, size, flags))
        if size != NN_MSG and nbytes != size and ensure_size:
            raise AssertionError('expect %d instead %d' % (size, nbytes))
        return nbytes


class Socket(SocketBase):

    def send(self, message, size=None, flags=0):
        return self._blocking_send(message, size, flags)

    def recv(self, message=None, size=None, flags=0):
        return self._blocking_recv(message, size, flags)


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

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *exc_info):
        return self.__exit__(*exc_info)  # XXX: Would this block?

    def shutdown(self):
        if self.socket.fd is None:
            self.endpoint_id = None
            return
        if self.endpoint_id is None:
            return
        endpoint_id, self.endpoint_id = self.endpoint_id, None
        errors.check(_nn.nn_shutdown(self.socket.fd, endpoint_id))
        self.socket.endpoints.pop(endpoint_id)


class BindEndpoint(EndpointBase):
    pass


class ConnectEndpoint(EndpointBase):
    pass


class OptionsProxy:

    def __init__(self, socket):
        self.socket = socket

    def _getopt(self, level, option):
        return self.socket.getsockopt(level, option)

    def _setopt(self, value, level, option):
        self.socket.setsockopt(level, option, value)

    def _make(getter, setter, varz):
        # Because partialmethod doesn't work with property...

        level_option_pairs = [
            (NN_SUB, NN_SUB_SUBSCRIBE),
            (NN_SUB, NN_SUB_UNSUBSCRIBE),
            (NN_REQ, NN_REQ_RESEND_IVL),
            (NN_SURVEYOR, NN_SURVEYOR_DEADLINE),
            (NN_TCP, NN_TCP_NODELAY),
            (NN_WS, NN_WS_MSG_TYPE),
        ]
        level_option_pairs.extend(
            (NN_SOL_SOCKET, option)
            for option in SocketOption
        )

        readonly = {
            NN_DOMAIN,
            NN_PROTOCOL,
            NN_SNDFD,
            NN_RCVFD,
        }

        for level, option in level_option_pairs:
            name = option.name.lower()
            prop = property(partial(getter, level=level, option=option))
            if option not in readonly:
                prop = prop.setter(partial(setter, level=level, option=option))
            varz[name] = prop

    _make(_getopt, _setopt, locals())

    del _make


def device(sock1, sock2=None):
    fd1 = sock1.fd
    fd2 = sock2.fd if sock2 is not None else -1
    errors.check(_nn.nn_device(fd1, fd2))


def terminate():
    _nn.nn_term()
