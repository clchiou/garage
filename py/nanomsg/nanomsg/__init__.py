__all__ = [
    'MessageBuffer',
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

errors.asserts(
    len(set(__all__)) == len(__all__),
    'expect no variable name conflict: %r', __all__,
)


_PyBUF_READ = 0x100
_PyBUF_WRITE = 0x200

_PyMemoryView_FromMemory = ctypes.pythonapi.PyMemoryView_FromMemory
_PyMemoryView_FromMemory.argtypes = [
    ctypes.c_void_p,
    ctypes.c_ssize_t,
    ctypes.c_int,
]
_PyMemoryView_FromMemory.restype = ctypes.py_object


class MessageBuffer:
    """Abstraction on top of nn_allocmsg, etc."""

    def __init__(self, size, allocation_type=0, *, buffer=None):
        if buffer:
            self.buffer, self.size = buffer, size
        else:
            self.buffer, self.size = None, 0
            self.buffer = _nn.nn_allocmsg(size, allocation_type)
            if self.buffer is None:
                raise NanomsgError.make(_nn.nn_errno())
            self.size = size

    def __repr__(self):
        if self.buffer is None:
            ptr, size = 0, 0
        else:
            ptr, size = self.buffer.value, self.size
        return ('<%s addr 0x%016x, size 0x%x>' %
                (self.__class__.__name__, ptr, size))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.free()

    def __del__(self):
        # Don't call super's __del__ since `object` doesn't have one.
        self.free()

    def as_memoryview(self):
        errors.asserts(self.buffer is not None, 'expect non-None buffer')
        return _PyMemoryView_FromMemory(
            self.buffer,
            self.size,
            _PyBUF_READ | _PyBUF_WRITE,
        )

    def resize(self, size):
        errors.asserts(self.buffer is not None, 'expect non-None buffer')
        buffer = _nn.nn_reallocmsg(self.buffer, size)
        if buffer is None:
            raise NanomsgError.make(_nn.nn_errno())
        self.buffer, self.size = buffer, size

    def disown(self):
        buffer, self.buffer, self.size = self.buffer, None, 0
        return buffer

    def free(self):
        if self.buffer is None:
            return
        errors.check(_nn.nn_freemsg(self.buffer))
        # It disowns the buffer only after nn_freemsg succeeds, but
        # honestly, if it can't free the buffer, I am not sure what's
        # the purpose to keep owning it (maybe for debugging?).
        self.disown()


class Message:
    """Abstraction on top of nn_msghdr.

    nn_msghdr is pretty configurable, but here we only support one (most
    common?) configuration that allocates both message header and body
    with nn_allocmsg.
    """

    def __init__(self):

        self._control = ctypes.c_void_p()
        self._message = ctypes.c_void_p()
        self.size = 0

        self._io_vector = _nn.nn_iovec()
        self._io_vector.iov_base = ctypes.addressof(self._message)
        self._io_vector.iov_len = NN_MSG

        self._message_header = _nn.nn_msghdr()
        ctypes.memset(
            ctypes.addressof(self._message_header),
            0x0,
            ctypes.sizeof(self._message_header),
        )
        self._message_header.msg_control = ctypes.addressof(self._control)
        self._message_header.msg_controllen = NN_MSG
        self._message_header.msg_iov = ctypes.pointer(self._io_vector)
        self._message_header.msg_iovlen = 1

    def __repr__(self):
        return '<%s control 0x%016x, message 0x%016x, size 0x%x>' % (
            self.__class__.__name__,
            self._control.value or 0,
            self._message.value or 0,
            self.size,
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.free()

    def __del__(self):
        # Don't call super's __del__ since `object` doesn't have one.
        self.free()

    @property
    def nn_msghdr(self):
        errors.asserts(
            self._message_header is not None, 'expect non-None msghdr')
        return self._message_header

    def as_memoryview(self):
        errors.asserts(self.size, 'expect non-zero message size')
        return _PyMemoryView_FromMemory(
            self._message,
            self.size,
            _PyBUF_READ | _PyBUF_WRITE,
        )

    def disown(self):
        self._control.value = None
        self._message.value = None
        self.size = 0
        self._message_header = None
        self._io_vector = None

    def free(self):
        self.size = 0
        self._message_header = None
        self._io_vector = None
        rc1 = rc2 = 0
        if self._control:
            rc1 = _nn.nn_freemsg(self._control)
            self._control.value = None
        if self._message:
            rc2 = _nn.nn_freemsg(self._message)
            self._message.value = None
        errors.check(rc1)
        errors.check(rc2)


class SocketBase:

    def __init__(self, *, domain=AF_SP, protocol=None, socket_fd=None):
        # Set fd to None as a safety measure in case subclass's __init__
        # raises exception since __del__ need at least self.fd.
        self.fd = None

        errors.asserts(
            (protocol is None) != (socket_fd is None),
            'expect either protocol or socket_fd is set: %r, %r',
            protocol, socket_fd,
        )
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
                raise AssertionError
        return ('<%s fd %r, listen on %r, connect to %r>' %
                (self.__class__.__name__, self.fd, binds, connects))

    #
    # Manage socket life cycle.
    #

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
        try:
            errors.check(_nn.nn_close(self.fd))
        except EBADF:
            # Suppress EBADF because socket might have been closed
            # through some other means, like nn_term.
            pass
        else:
            self.fd = None
            self.endpoints.clear()

    #
    # Socket options.
    #

    def getsockopt(self, level, option, option_size=64):
        errors.asserts(self.fd is not None, 'expect socket.fd')

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
        errors.asserts(self.fd is not None, 'expect socket.fd')

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

    #
    # Endpoints.
    #

    def bind(self, address):
        errors.asserts(self.fd is not None, 'expect socket.fd')
        return self.__make_endpoint(address, BindEndpoint, _nn.nn_bind)

    def connect(self, address):
        errors.asserts(self.fd is not None, 'expect socket.fd')
        return self.__make_endpoint(address, ConnectEndpoint, _nn.nn_connect)

    def __make_endpoint(self, address, ep_class, ep_make):
        if isinstance(address, str):
            address_bytes = address.encode('ascii')
        else:
            address_bytes = address
        endpoint_id = errors.check(ep_make(self.fd, address_bytes))
        endpoint = ep_class(self, endpoint_id, address)
        self.endpoints[endpoint_id] = endpoint
        return endpoint

    #
    # Private data transmission methods that sub-classes may call.
    #

    def _send_message_buffer(self, message, flags):
        nbytes = self._send_buffer(message.buffer, NN_MSG, flags)
        message.disown()
        return nbytes

    def _send_message(self, message, flags):
        size = message.size
        nbytes = errors.check(_nn.nn_sendmsg(
            self.fd,
            ctypes.pointer(message.nn_msghdr),
            flags,
        ))
        message.disown()
        if nbytes != size:
            raise AssertionError('expect size = %d, not %d' % (size, nbytes))
        return nbytes

    def _send_buffer(self, buffer, size, flags):
        return self.__transmit(_nn.nn_send, buffer, size, flags, True)

    def _recv_message_buffer(self, void_p, flags):
        nbytes = self._recv_buffer(ctypes.byref(void_p), NN_MSG, flags)
        return MessageBuffer(buffer=void_p, size=nbytes)

    def _recv_message(self, message, flags):
        if message is None:
            message = Message()
            return_message = True
        else:
            return_message = False
        nbytes = errors.check(_nn.nn_recvmsg(
            self.fd,
            ctypes.pointer(message.nn_msghdr),
            flags | NN_DONTWAIT,
        ))
        message.size = nbytes
        if return_message:
            return message
        else:
            return nbytes

    def _recv_buffer(self, buffer, size, flags):
        return self.__transmit(_nn.nn_recv, buffer, size, flags, False)

    def __transmit(self, nn_func, buffer, size, flags, ensure_size):
        nbytes = errors.check(nn_func(self.fd, buffer, size, flags))
        if size != NN_MSG and nbytes != size and ensure_size:
            raise AssertionError('expect size = %d, not %d' % (size, nbytes))
        return nbytes


class Socket(SocketBase):

    def send(self, message, size=None, flags=0):
        errors.asserts(self.fd is not None, 'expect socket.fd')
        errors.asserts(
            not isinstance(message, Message), 'send does not accept Message')
        if isinstance(message, MessageBuffer):
            return self._send_message_buffer(message, flags)
        else:
            if size is None:
                size = len(message)
            return self._send_buffer(message, size, flags)

    def recv(self, message=None, size=None, flags=0):
        errors.asserts(self.fd is not None, 'expect socket.fd')
        errors.asserts(
            not isinstance(message, Message), 'recv does not accept Message')
        if message is None:
            return self._recv_message_buffer(ctypes.c_void_p(), flags)
        else:
            errors.asserts(size is not None, 'expect size')
            return self._recv_buffer(message, size, flags)


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
