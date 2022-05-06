__all__ = [
    'ContextBase',
    'DialerBase',
    'Protocols',
    'SocketBase',
]

import ctypes
import enum

from g1.bases import classes
from g1.bases.assertions import ASSERT

from . import _nng
from . import errors
from . import options

Protocols = enum.Enum(
    'Protocols',
    [(
        name.upper(),
        (
            _nng.F['nng_%s_open' % name],
            _nng.F['nng_%s_open_raw' % name],
        ),
    ) for name in _nng.PROTOCOLS],
)


class CommonOptions(options.OptionsBase):

    # Generic options.

    raw = options.make(_nng.Options.NNG_OPT_RAW)

    protocol_id = options.make(_nng.Options.NNG_OPT_PROTO)
    protocol_name = options.make(_nng.Options.NNG_OPT_PROTONAME)

    peer_id = options.make(_nng.Options.NNG_OPT_PEER)
    peer_name = options.make(_nng.Options.NNG_OPT_PEERNAME)

    recv_fd = options.make(_nng.Options.NNG_OPT_RECVFD)
    send_fd = options.make(_nng.Options.NNG_OPT_SENDFD)

    max_recv_size = options.make(_nng.Options.NNG_OPT_RECVMAXSZ)


class ContextOptions(options.OptionsBase):

    # Generic options.

    recv_timeout = options.make(_nng.Options.NNG_OPT_RECVTIMEO)
    send_timeout = options.make(_nng.Options.NNG_OPT_SENDTIMEO)

    # Protocol "pubsub0" options.

    def subscribe(self, topic):
        options.setopt_bytes(
            self, _nng.Options.NNG_OPT_SUB_SUBSCRIBE[0], topic
        )

    def unsubscribe(self, topic):
        options.setopt_bytes(
            self, _nng.Options.NNG_OPT_SUB_UNSUBSCRIBE[0], topic
        )

    # Protocol "reqrep0" options.

    resend_time = options.make(_nng.Options.NNG_OPT_REQ_RESENDTIME)

    # Protocol "survey0" options.

    survey_time = options.make(_nng.Options.NNG_OPT_SURVEYOR_SURVEYTIME)


class SocketBase(CommonOptions, ContextOptions):

    _name = 'socket'

    # Generic options.

    name = options.make(_nng.Options.NNG_OPT_SOCKNAME)

    recv_buffer_size = options.make(_nng.Options.NNG_OPT_RECVBUF)
    send_buffer_size = options.make(_nng.Options.NNG_OPT_SENDBUF)

    max_ttl = options.make(_nng.Options.NNG_OPT_MAXTTL)

    min_reconnect_time = options.make(_nng.Options.NNG_OPT_RECONNMINT)
    max_reconnect_time = options.make(_nng.Options.NNG_OPT_RECONNMAXT)

    # TCP options.

    tcp_nodelay = options.make(_nng.Options.NNG_OPT_TCP_NODELAY)
    tcp_keepalive = options.make(_nng.Options.NNG_OPT_TCP_KEEPALIVE)

    # End of options.

    _dialer_type = classes.abstract_method
    dial = classes.abstract_method
    send = classes.abstract_method
    recv = classes.abstract_method
    sendmsg = classes.abstract_method
    recvmsg = classes.abstract_method

    def __init__(self, protocol, *, raw=False):

        # In case ``__init__`` raises.
        self._handle = None

        ASSERT.isinstance(protocol, Protocols)
        opener = protocol.value[1] if raw else protocol.value[0]
        handle = _nng.nng_socket()
        errors.check(opener(ctypes.byref(handle)))
        self._handle = handle.value
        self.protocol = protocol
        self.dialers = {}
        self.listeners = {}

    __repr__ = classes.make_repr(
        'id={self.id} dialers={self.dialers} listeners={self.listeners}'
    )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        # You have to check whether ``__init__`` raises.
        if self._handle is not None:
            self.close()

    @property
    def id(self):
        return _nng.F.nng_socket_id(self._handle)

    def close(self):
        try:
            errors.check(_nng.F.nng_close(self._handle))
        except errors.Errors.ECLOSED:
            pass
        self.dialers.clear()
        self.listeners.clear()

    def _dial(self, url, *, flags=0, create_only=False):

        handle = _nng.nng_dialer()
        handle_p = ctypes.byref(handle)

        url = _nng.ensure_bytes(url)

        if create_only:
            rv = _nng.F.nng_dialer_create(handle_p, self._handle, url)
        else:
            rv = _nng.F.nng_dial(self._handle, url, handle_p, flags)
        errors.check(rv)

        dialer = self._dialer_type(self, handle.value)
        self.dialers[dialer.id] = dialer

        return dialer

    def listen(self, url, *, create_only=False):

        handle = _nng.nng_listener()
        handle_p = ctypes.byref(handle)

        url = _nng.ensure_bytes(url)

        if create_only:
            rv = _nng.F.nng_listener_create(handle_p, self._handle, url)
        else:
            rv = _nng.F.nng_listen(self._handle, url, handle_p, 0)
        errors.check(rv)

        listener = Listener(self, handle.value)
        self.listeners[listener.id] = listener

        return listener


class ContextBase(ContextOptions):

    _name = 'ctx'

    send = classes.abstract_method
    recv = classes.abstract_method
    sendmsg = classes.abstract_method
    recvmsg = classes.abstract_method

    def __init__(self, socket):

        # In case ``__init__`` raises.
        self._handle = None

        handle = _nng.nng_ctx()
        errors.check(_nng.F.nng_ctx_open(ctypes.byref(handle), socket._handle))
        self.socket = socket
        self._handle = handle

    __repr__ = classes.make_repr('id={self.id} {self.socket}')

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        # You have to check whether ``__init__`` raises.
        if self._handle is not None:
            self.close()

    @property
    def id(self):
        return _nng.F.nng_ctx_id(self._handle)

    def close(self):
        try:
            errors.check(_nng.F.nng_ctx_close(self._handle))
        except errors.Errors.ECLOSED:
            pass


class Endpoint(CommonOptions):

    # Generic options.

    name = options.make(_nng.Options.NNG_OPT_SOCKNAME, mode='ro')

    recv_buffer_size = options.make(_nng.Options.NNG_OPT_RECVBUF, mode='ro')
    send_buffer_size = options.make(_nng.Options.NNG_OPT_SENDBUF, mode='ro')

    local_address = options.make(_nng.Options.NNG_OPT_LOCADDR)
    remote_address = options.make(_nng.Options.NNG_OPT_REMADDR)

    url = options.make(_nng.Options.NNG_OPT_URL)

    max_ttl = options.make(_nng.Options.NNG_OPT_MAXTTL, mode='ro')

    # TCP options.

    tcp_nodelay = options.make(_nng.Options.NNG_OPT_TCP_NODELAY, mode='ro')
    tcp_keepalive = options.make(_nng.Options.NNG_OPT_TCP_KEEPALIVE, mode='ro')

    tcp_bound_port = options.make(_nng.Options.NNG_OPT_TCP_BOUND_PORT)

    # TLS options.

    tls_auth_mode = options.make(_nng.Options.NNG_OPT_TLS_AUTH_MODE)
    tls_cert_key_file = options.make(_nng.Options.NNG_OPT_TLS_CERT_KEY_FILE)
    tls_ca_file = options.make(_nng.Options.NNG_OPT_TLS_CA_FILE)
    tls_server_name = options.make(_nng.Options.NNG_OPT_TLS_SERVER_NAME)
    tls_verified = options.make(_nng.Options.NNG_OPT_TLS_VERIFIED)

    # WebSocket options.

    ws_request_headers = options.make(_nng.Options.NNG_OPT_WS_REQUEST_HEADERS)
    ws_response_headers = options.make(
        _nng.Options.NNG_OPT_WS_RESPONSE_HEADERS
    )

    ws_request_uri = options.make(_nng.Options.NNG_OPT_WS_REQUEST_URI)

    ws_max_send_frame = options.make(_nng.Options.NNG_OPT_WS_SENDMAXFRAME)
    ws_max_recv_frame = options.make(_nng.Options.NNG_OPT_WS_RECVMAXFRAME)

    ws_protocol = options.make(_nng.Options.NNG_OPT_WS_PROTOCOL)

    def ws_request_get_header(self, name):
        name = (
            _nng.Options.NNG_OPT_WS_REQUEST_HEADER[0] +
            _nng.ensure_bytes(name)
        )
        return options.getopt_string(self, name)

    def ws_request_set_header(self, name, value):
        name = (
            _nng.Options.NNG_OPT_WS_REQUEST_HEADER[0] +
            _nng.ensure_bytes(name)
        )
        options.setopt_string(self, name, value)
        return value

    def ws_response_get_header(self, name):
        name = (
            _nng.Options.NNG_OPT_WS_RESPONSE_HEADER[0] +
            _nng.ensure_bytes(name)
        )
        return options.getopt_string(self, name)

    def ws_response_set_header(self, name, value):
        name = (
            _nng.Options.NNG_OPT_WS_RESPONSE_HEADER[0] +
            _nng.ensure_bytes(name)
        )
        options.setopt_string(self, name, value)
        return value

    # End of options.

    _endpoints = classes.abstract_property
    _get_id = classes.abstract_method
    _close = classes.abstract_method

    def __init__(self, socket, handle):
        self._socket = socket
        self._handle = handle

    __repr__ = classes.make_repr('id={self.id}')

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @property
    def id(self):
        return self._get_id(self._handle)

    def close(self):
        try:
            errors.check(self._close(self._handle))
        except errors.Errors.ECLOSED:
            pass
        getattr(self._socket, self._endpoints).pop(self.id)


class DialerBase(Endpoint):

    _name = 'dialer'

    # Generic options.

    min_reconnect_time = options.make(_nng.Options.NNG_OPT_RECONNMINT)
    max_reconnect_time = options.make(_nng.Options.NNG_OPT_RECONNMAXT)

    # End of options.

    _endpoints = 'dialers'
    _get_id = _nng.F.nng_dialer_id
    _close = _nng.F.nng_dialer_close

    def _start(self, *, flags=0):
        errors.check(_nng.F.nng_dialer_start(self._handle, flags))


class Listener(Endpoint):

    _name = 'listener'

    # Generic options.

    min_reconnect_time = options.make(
        _nng.Options.NNG_OPT_RECONNMINT, mode='ro'
    )
    max_reconnect_time = options.make(
        _nng.Options.NNG_OPT_RECONNMAXT, mode='ro'
    )

    # End of options.

    _endpoints = 'listeners'
    _get_id = _nng.F.nng_listener_id
    _close = _nng.F.nng_listener_close

    def start(self):
        errors.check(_nng.F.nng_listener_start(self._handle, 0))
