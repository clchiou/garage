"""ctypes-based libnng binding."""

__all__ = [
    'F',
    'NNG_DURATION_INFINITE',
    'NNG_DURATION_DEFAULT',
    'NNG_DURATION_ZERO',
    'NNG_MAXADDRLEN',
    'OPTION_TYPES',
    'PROTOCOLS',
    'ensure_bytes',
    # Enum types.
    'Durations',
    'Options',
    'nng_errno_enum',
    'nng_flag_enum',
    'nng_sockaddr_family',
    # Handle types.
    'nng_ctx',
    'nng_dialer',
    'nng_listener',
    'nng_pipe',
    'nng_socket',
    # Message type.
    'nng_aio_callback',
    'nng_aio_p',
    'nng_msg_p',
    # Structures and unions.
    'nng_sockaddr_in',
    'nng_sockaddr_in6',
    'nng_sockaddr_inproc',
    'nng_sockaddr_ipc',
    'nng_sockaddr_zt',
    'nng_sockaddr',
]

import enum
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    Union,
    c_bool,
    c_char,
    c_char_p,
    c_int,
    c_int32,
    c_size_t,
    c_uint16,
    c_uint32,
    c_uint64,
    c_uint8,
    c_void_p,
    cdll,
)

from g1.bases import collections
from g1.bases.assertions import ASSERT

LIBNNG = cdll.LoadLibrary('libnng.so')

PROTOCOLS = (
    # bus
    'bus0',
    # pair
    'pair0',
    'pair1',
    # pipeline
    'pull0',
    'push0',
    # pubsub
    'pub0',
    'sub0',
    # reqrep
    'rep0',
    'req0',
    # survey
    'respondent0',
    'surveyor0',
)

c_bool_p = POINTER(c_bool)
c_char_p_p = POINTER(c_char_p)
c_int_p = POINTER(c_int)
c_size_t_p = POINTER(c_size_t)
c_uint64_p = POINTER(c_uint64)
c_void_p_p = POINTER(c_void_p)

nng_ctx = c_uint32
nng_dialer = c_uint32
nng_listener = c_uint32
nng_pipe = c_uint32
nng_socket = c_uint32

nng_duration = c_int32

NNG_DURATION_INFINITE = -1
NNG_DURATION_DEFAULT = -2
NNG_DURATION_ZERO = 0

nng_ctx_p = POINTER(nng_ctx)
nng_dialer_p = POINTER(nng_dialer)
nng_listener_p = POINTER(nng_listener)
nng_pipe_p = POINTER(nng_pipe)
nng_socket_p = POINTER(nng_socket)

nng_duration_p = POINTER(nng_duration)

nng_aio_p = c_void_p
nng_aio_p_p = POINTER(nng_aio_p)

nng_aio_callback = CFUNCTYPE(None, c_void_p)

nng_msg_p = c_void_p
nng_msg_p_p = POINTER(nng_msg_p)

NNG_MAXADDRLEN = 128

_nng_address = c_char * NNG_MAXADDRLEN


class nng_sockaddr_inproc(Structure):
    _fields_ = [
        ('sa_family', c_uint16),
        ('sa_name', _nng_address),
    ]


class nng_sockaddr_path(Structure):
    _fields_ = [
        ('sa_family', c_uint16),
        ('sa_path', _nng_address),
    ]


nng_sockaddr_ipc = nng_sockaddr_path


class nng_sockaddr_in6(Structure):
    _fields_ = [
        ('sa_family', c_uint16),
        ('sa_port', c_uint16),
        ('sa_addr', c_uint8 * 16),
    ]


class nng_sockaddr_in(Structure):
    _fields_ = [
        ('sa_family', c_uint16),
        ('sa_port', c_uint16),
        ('sa_addr', c_uint32),
    ]


class nng_sockaddr_zt(Structure):
    _fields_ = [
        ('sa_family', c_uint16),
        ('sa_nwid', c_uint64),
        ('sa_nodeid', c_uint64),
        ('sa_port', c_uint32),
    ]


class nng_sockaddr(Union):
    _fields_ = [
        ('sa_family', c_uint16),
        ('s_ipc', nng_sockaddr_ipc),
        ('s_inproc', nng_sockaddr_inproc),
        ('s_in6', nng_sockaddr_in6),
        ('s_in', nng_sockaddr_in),
        ('s_zt', nng_sockaddr_zt),
    ]


nng_sockaddr_p = POINTER(nng_sockaddr)


@enum.unique
class Durations(enum.IntEnum):
    INFINITE = NNG_DURATION_INFINITE
    DEFAULT = NNG_DURATION_DEFAULT


@enum.unique
class nng_sockaddr_family(enum.IntEnum):
    NNG_AF_UNSPEC = 0
    NNG_AF_INPROC = 1
    NNG_AF_IPC = 2
    NNG_AF_INET = 3
    NNG_AF_INET6 = 4
    NNG_AF_ZT = 5


@enum.unique
class nng_flag_enum(enum.IntEnum):
    NNG_FLAG_ALLOC = 1
    NNG_FLAG_NONBLOCK = 2


@enum.unique
class nng_errno_enum(enum.IntEnum):
    NNG_EINTR = 1
    NNG_ENOMEM = 2
    NNG_EINVAL = 3
    NNG_EBUSY = 4
    NNG_ETIMEDOUT = 5
    NNG_ECONNREFUSED = 6
    NNG_ECLOSED = 7
    NNG_EAGAIN = 8
    NNG_ENOTSUP = 9
    NNG_EADDRINUSE = 10
    NNG_ESTATE = 11
    NNG_ENOENT = 12
    NNG_EPROTO = 13
    NNG_EUNREACHABLE = 14
    NNG_EADDRINVAL = 15
    NNG_EPERM = 16
    NNG_EMSGSIZE = 17
    NNG_ECONNABORTED = 18
    NNG_ECONNRESET = 19
    NNG_ECANCELED = 20
    NNG_ENOFILES = 21
    NNG_ENOSPC = 22
    NNG_EEXIST = 23
    NNG_EREADONLY = 24
    NNG_EWRITEONLY = 25
    NNG_ECRYPTO = 26
    NNG_EPEERAUTH = 27
    NNG_ENOARG = 28
    NNG_EAMBIGUOUS = 29
    NNG_EBADTYPE = 30
    NNG_EINTERNAL = 1000
    NNG_ESYSERR = 0x10000000
    NNG_ETRANERR = 0x20000000


# This is a list of common option types, which does not include
# "sockaddr", etc.
OPTION_TYPES = {
    # name -> (getter_argtype, setter_argtype).
    'bool': (c_bool_p, c_bool),
    'int': (c_int_p, c_int),
    'ms': (nng_duration_p, nng_duration),
    'size': (c_size_t_p, c_size_t),
    'uint64': (c_uint64_p, c_uint64),
    'string': (c_char_p_p, c_char_p),
    'ptr': (c_void_p_p, c_void_p),
}


@enum.unique
class Options(tuple, enum.Enum):

    #
    # Generic options.
    #

    NNG_OPT_SOCKNAME = (b'socket-name', 'string', 'rw')
    NNG_OPT_RAW = (b'raw', 'bool', 'ro')
    NNG_OPT_PROTO = (b'protocol', 'int', 'ro')
    NNG_OPT_PROTONAME = (b'protocol-name', 'string', 'ro')
    NNG_OPT_PEER = (b'peer', 'int', 'ro')
    NNG_OPT_PEERNAME = (b'peer-name', 'string', 'ro')
    NNG_OPT_RECVBUF = (b'recv-buffer', 'int', 'rw')
    NNG_OPT_SENDBUF = (b'send-buffer', 'int', 'rw')
    NNG_OPT_RECVFD = (b'recv-fd', 'int', 'ro')
    NNG_OPT_SENDFD = (b'send-fd', 'int', 'ro')
    NNG_OPT_RECVTIMEO = (b'recv-timeout', 'ms', 'rw')
    NNG_OPT_SENDTIMEO = (b'send-timeout', 'ms', 'rw')
    NNG_OPT_LOCADDR = (b'local-address', 'sockaddr', 'ro')
    NNG_OPT_REMADDR = (b'remote-address', 'sockaddr', 'ro')
    NNG_OPT_URL = (b'url', 'string', 'ro')
    NNG_OPT_MAXTTL = (b'ttl-max', 'int', 'rw')
    NNG_OPT_RECVMAXSZ = (b'recv-size-max', 'size', 'rw')
    NNG_OPT_RECONNMINT = (b'reconnect-time-min', 'ms', 'rw')
    NNG_OPT_RECONNMAXT = (b'reconnect-time-max', 'ms', 'rw')

    #
    # Transport options.
    #

    # TLS options.
    NNG_OPT_TLS_CONFIG = (b'tls-config', 'ptr', 'rw')
    NNG_OPT_TLS_AUTH_MODE = (b'tls-authmode', 'int', 'wo')
    NNG_OPT_TLS_CERT_KEY_FILE = (b'tls-cert-key-file', 'string', 'wo')
    NNG_OPT_TLS_CA_FILE = (b'tls-ca-file', 'string', 'wo')
    NNG_OPT_TLS_SERVER_NAME = (b'tls-server-name', 'string', 'wo')
    NNG_OPT_TLS_VERIFIED = (b'tls-verified', 'bool', 'ro')

    # TCP options.
    NNG_OPT_TCP_NODELAY = (b'tcp-nodelay', 'bool', 'rw')
    NNG_OPT_TCP_KEEPALIVE = (b'tcp-keepalive', 'bool', 'rw')
    NNG_OPT_TCP_BOUND_PORT = (b'tcp-bound-port', 'int', 'ro')

    # IPC options.
    NNG_OPT_IPC_SECURITY_DESCRIPTOR = (b'ipc:security-descriptor', 'ptr', 'wo')
    NNG_OPT_IPC_PERMISSIONS = (b'ipc:permissions', 'int', 'wo')
    NNG_OPT_IPC_PEER_UID = (b'ipc:peer-uid', 'uint64', 'ro')
    NNG_OPT_IPC_PEER_GID = (b'ipc:peer-gid', 'uint64', 'ro')
    NNG_OPT_IPC_PEER_PID = (b'ipc:peer-pid', 'uint64', 'ro')
    NNG_OPT_IPC_PEER_ZONEID = (b'ipc:peer-zoneid', 'uint64', 'ro')

    # WebSocket options.

    # Note that ``NNG_OPT_WS_REQUEST_HEADERS`` is read-only for some
    # and write-only for some.
    NNG_OPT_WS_REQUEST_HEADERS = (b'ws:request-headers', 'string', 'rw')

    # Note that ``NNG_OPT_WS_RESPONSE_HEADERS`` is read-only for some
    # and write-only for some.
    NNG_OPT_WS_RESPONSE_HEADERS = (b'ws:response-headers', 'string', 'rw')

    # Note that ``NNG_OPT_WS_REQUEST_HEADER`` is a dynamic property.
    NNG_OPT_WS_REQUEST_HEADER = (b'ws:request-header:', 'string', 'rw')

    # Note that ``NNG_OPT_WS_RESPONSE_HEADER`` is a dynamic property.
    NNG_OPT_WS_RESPONSE_HEADER = (b'ws:response-header:', 'string', 'rw')

    NNG_OPT_WS_REQUEST_URI = (b'ws:request-uri', 'string', 'ro')
    NNG_OPT_WS_SENDMAXFRAME = (b'ws:txframe-max', 'size', 'rw')
    NNG_OPT_WS_RECVMAXFRAME = (b'ws:rxframe-max', 'size', 'rw')
    NNG_OPT_WS_PROTOCOL = (b'ws:protocol', 'string', 'rw')

    #
    # Protocol options.
    #

    # Protocol "pair1" options.
    NNG_OPT_PAIR1_POLY = (b'pair1:polyamorous', 'bool', 'rw')

    # Protocol "pubsub0" options.
    NNG_OPT_SUB_SUBSCRIBE = (b'sub:subscribe', 'string', 'rw')
    NNG_OPT_SUB_UNSUBSCRIBE = (b'sub:unsubscribe', 'string', 'rw')

    # Protocol "reqrep0" options.
    NNG_OPT_REQ_RESENDTIME = (b'req:resend-time', 'ms', 'rw')

    # Protocol "survey0" options.
    NNG_OPT_SURVEYOR_SURVEYTIME = (b'surveyor:survey-time', 'ms', 'rw')


def load_func(name, restype, argtypes):
    func = LIBNNG[name]
    func.argtypes = argtypes
    func.restype = restype
    return func


# Polyfill this function.  API document says nng implements this, but it
# actually does not.  (Maybe a bug?)
ASSERT.false(hasattr(LIBNNG, 'nng_ctx_setopt_string'))


def nng_ctx_setopt_string(handle, name, value):
    return F.nng_ctx_setopt(handle, name, value, len(value))


F = collections.Namespace(
    *(
        (args[0], load_func(*args)) for args in (

            # Common functions.
            ('nng_closeall', None, ()),
            ('nng_strerror', c_char_p, (c_int, )),
            ('nng_strfree', None, (c_char_p, )),
            ('nng_free', None, (c_void_p, c_size_t)),

            # Socket functions.
            ('nng_socket_id', c_int, (nng_socket, )),
            ('nng_close', c_int, (nng_socket, )),
            ('nng_getopt', c_int, (nng_socket, c_char_p, c_void_p, c_size_t)),
            ('nng_setopt', c_int, (nng_socket, c_char_p, c_void_p, c_size_t)),
            *(('nng_getopt_%s' % n, c_int, (nng_socket, c_char_p, t))
              for n, (t, _) in OPTION_TYPES.items()),
            *(('nng_setopt_%s' % n, c_int, (nng_socket, c_char_p, t))
              for n, (_, t) in OPTION_TYPES.items()),
            ('nng_send', c_int, (nng_socket, c_void_p, c_size_t, c_int)),
            ('nng_recv', c_int, (nng_socket, c_void_p, c_size_t_p, c_int)),
            ('nng_sendmsg', c_int, (nng_socket, nng_msg_p, c_int)),
            ('nng_recvmsg', c_int, (nng_socket, nng_msg_p_p, c_int)),
            ('nng_send_aio', None, (nng_socket, nng_aio_p)),
            ('nng_recv_aio', None, (nng_socket, nng_aio_p)),

            # Context functions.
            ('nng_ctx_open', c_int, (nng_ctx_p, nng_socket)),
            ('nng_ctx_id', c_int, (nng_ctx, )),
            ('nng_ctx_close', c_int, (nng_ctx, )),
            ('nng_ctx_getopt', c_int, (nng_ctx, c_char_p, c_void_p, c_size_t)),
            ('nng_ctx_setopt', c_int, (nng_ctx, c_char_p, c_void_p, c_size_t)),
            *(('nng_ctx_getopt_%s' % n, c_int, (nng_ctx, c_char_p, t))
              for n, (t, _) in OPTION_TYPES.items()
              if n in ('bool', 'int', 'ms', 'size')),
            *(('nng_ctx_setopt_%s' % n, c_int, (nng_ctx, c_char_p, t))
              for n, (_, t) in OPTION_TYPES.items()
              if n in ('bool', 'int', 'ms', 'size')),
            ('nng_ctx_send', None, (nng_ctx, nng_aio_p)),
            ('nng_ctx_recv', None, (nng_ctx, nng_aio_p)),

            # Protocols.
            *(('nng_%s_open' % name, c_int, (nng_socket_p, ))
              for name in PROTOCOLS),
            *(('nng_%s_open_raw' % name, c_int, (nng_socket_p, ))
              for name in PROTOCOLS),

            # Dialer functions.
            ('nng_dial', c_int, (nng_socket, c_char_p, nng_dialer_p, c_int)),
            ('nng_dialer_create', c_int, (nng_dialer_p, nng_socket, c_char_p)),
            ('nng_dialer_start', c_int, (nng_dialer, c_int)),
            ('nng_dialer_id', c_int, (nng_dialer, )),
            ('nng_dialer_close', c_int, (nng_dialer, )),
            (
                'nng_dialer_getopt',
                c_int,
                (nng_dialer, c_char_p, c_void_p, c_size_t),
            ),
            (
                'nng_dialer_setopt',
                c_int,
                (nng_dialer, c_char_p, c_void_p, c_size_t),
            ),
            *(('nng_dialer_getopt_%s' % n, c_int, (nng_dialer, c_char_p, t))
              for n, (t, _) in OPTION_TYPES.items()),
            *(('nng_dialer_setopt_%s' % n, c_int, (nng_dialer, c_char_p, t))
              for n, (_, t) in OPTION_TYPES.items()),
            (
                'nng_dialer_getopt_sockaddr',
                c_int,
                (nng_dialer, c_char_p, nng_sockaddr_p),
            ),

            # Listener functions.
            (
                'nng_listen',
                c_int,
                (nng_socket, c_char_p, nng_listener_p, c_int),
            ),
            (
                'nng_listener_create',
                c_int,
                (nng_listener_p, nng_socket, c_char_p),
            ),
            ('nng_listener_start', c_int, (nng_listener, c_int)),
            ('nng_listener_id', c_int, (nng_listener, )),
            ('nng_listener_close', c_int, (nng_listener, )),
            (
                'nng_listener_getopt',
                c_int,
                (nng_listener, c_char_p, c_void_p, c_size_t),
            ),
            (
                'nng_listener_setopt',
                c_int,
                (nng_listener, c_char_p, c_void_p, c_size_t),
            ),
            *((
                'nng_listener_getopt_%s' % n,
                c_int,
                (nng_listener, c_char_p, t),
            ) for n, (t, _) in OPTION_TYPES.items()),
            *((
                'nng_listener_setopt_%s' % n,
                c_int,
                (nng_listener, c_char_p, t),
            ) for n, (_, t) in OPTION_TYPES.items()),
            (
                'nng_listener_getopt_sockaddr',
                c_int,
                (nng_listener, c_char_p, nng_sockaddr_p),
            ),

            # Message functions.
            ('nng_msg_alloc', c_int, (nng_msg_p_p, c_size_t)),
            ('nng_msg_dup', c_int, (nng_msg_p_p, nng_msg_p)),
            ('nng_msg_free', None, (nng_msg_p, )),
            # Message header functions.
            ('nng_msg_header', c_void_p, (nng_msg_p, )),
            ('nng_msg_header_len', c_size_t, (nng_msg_p, )),
            ('nng_msg_header_append', c_int, (nng_msg_p, c_void_p, c_size_t)),
            ('nng_msg_header_clear', None, (nng_msg_p, )),
            # Message body functions.
            ('nng_msg_body', c_void_p, (nng_msg_p, )),
            ('nng_msg_len', c_size_t, (nng_msg_p, )),
            ('nng_msg_append', c_int, (nng_msg_p, c_void_p, c_size_t)),
            ('nng_msg_clear', None, (nng_msg_p, )),

            # AIO functions.
            ('nng_aio_alloc', c_int, (nng_aio_p_p, c_void_p, c_void_p)),
            ('nng_aio_free', None, (nng_aio_p, )),
            ('nng_aio_set_timeout', None, (nng_aio_p, nng_duration)),
            ('nng_aio_set_msg', None, (nng_aio_p, nng_msg_p)),
            ('nng_aio_cancel', None, (nng_aio_p, )),
            ('nng_aio_wait', None, (nng_aio_p, )),
            ('nng_aio_result', c_int, (nng_aio_p, )),
            ('nng_aio_get_msg', nng_msg_p, (nng_aio_p, )),
        )
    ),
    nng_ctx_setopt_string=nng_ctx_setopt_string,
)


def ensure_bytes(str_or_bytes):
    if isinstance(str_or_bytes, str):
        str_or_bytes = str_or_bytes.encode('utf8')
    return str_or_bytes
