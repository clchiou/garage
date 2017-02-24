"""Define nghttp2 ABI."""

# We will populate __all__ with the "declare" functions below
__all__ = [
    'Nghttp2Error',
]

from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    Union,
    cdll,
    c_char_p,
    c_int,
    c_int32,
    c_size_t,
    c_ssize_t,
    c_uint32,
    c_uint8,
    c_void_p,
)

from enum import (
    IntEnum,
    IntFlag,
)


libnghttp2 = cdll.LoadLibrary('libnghttp2.so')


class Nghttp2Error(Exception):

    def __init__(self, error_code, message):
        super().__init__(message)
        self.error_code = error_code


def declare(name, value):
    __all__.append(name)
    globals()[name] = value


def declare_enum(enum_class):
    __all__.append(enum_class.__name__)
    __all__.extend(enum_class.__members__.keys())
    globals().update(enum_class.__members__)
    return enum_class


def declare_functions(func_decls):
    __all__.extend(name for name, _, _ in func_decls)
    globals().update(
        (name, _make_checked(name, func))
        for name, func in _iter_functions(func_decls)
    )


def declare_unchecked_functions(func_decls):
    __all__.extend(name for name, _, _ in func_decls)
    globals().update(_iter_functions(func_decls))


def _iter_functions(func_decls):
    for name, restype, argtypes in func_decls:
        func = getattr(libnghttp2, name)
        func.restype = restype
        func.argtypes = argtypes
        yield name, func


def _make_checked(name, unchecked):
    def checked(*args):
        rc = unchecked(*args)
        if rc < 0:
            msg = nghttp2_strerror(rc).decode('utf-8')
            raise Nghttp2Error(rc, '%s: %s' % (name, msg))
        return rc
    checked.unchecked = unchecked
    return checked


def declare_function_signatures(func_decls):
    __all__.extend(name for name, _, _ in func_decls)
    globals().update(
        (name, CFUNCTYPE(restype, *argtypes))
        for name, restype, argtypes in func_decls
    )


def declare_struct(struct):
    __all__.append(struct.__name__)
    return struct


# NOTE: We will assume all storage types for C enum is int (nghttp2 does
# not specify enum storage type)
c_enum = c_int


# Represent not NULL-terminated strings
c_uint8_p = c_void_p


### Macro constants


declare('NGHTTP2_INITIAL_WINDOW_SIZE', (1 << 16) - 1)


### Enums


@declare_enum
class nghttp2_error(IntEnum):
    NGHTTP2_ERR_CALLBACK_FAILURE = -902


@declare_enum
class nghttp2_nv_flag(IntFlag):
    NGHTTP2_NV_FLAG_NONE = 0


@declare_enum
class nghttp2_frame_type(IntEnum):
    NGHTTP2_DATA = 0
    NGHTTP2_HEADERS = 0x01
    NGHTTP2_SETTINGS = 0x04
    NGHTTP2_PUSH_PROMISE = 0x05


@declare_enum
class nghttp2_flag(IntEnum):
    NGHTTP2_FLAG_NONE = 0
    NGHTTP2_FLAG_END_STREAM = 0x01
    NGHTTP2_FLAG_ACK = 0x01


@declare_enum
class nghttp2_settings_id(IntEnum):
    NGHTTP2_SETTINGS_MAX_CONCURRENT_STREAMS = 0x03
    NGHTTP2_SETTINGS_INITIAL_WINDOW_SIZE = 0x04


@declare_enum
class nghttp2_error_code(IntEnum):
    NGHTTP2_NO_ERROR = 0x00
    NGHTTP2_INTERNAL_ERROR = 0x02


@declare_enum
class nghttp2_data_flag(IntFlag):
    NGHTTP2_DATA_FLAG_EOF = 0x01


@declare_enum
class nghttp2_headers_category(IntEnum):
    NGHTTP2_HCAT_REQUEST = 0


### Forward declarations


@declare_struct
class nghttp2_session(Structure):
    pass


@declare_struct
class nghttp2_data_source(Union):
    pass


@declare_struct
class nghttp2_frame(Union):
    pass


### Function signatures (callbacks)


declare_function_signatures([
    ('nghttp2_data_source_read_callback', c_ssize_t, (
        POINTER(nghttp2_session),  # session
        c_int32,  # stream_id
        c_uint8_p,  # buf
        c_size_t,  # length
        POINTER(c_uint32),  # data_flags
        POINTER(nghttp2_data_source),  # source
        c_void_p,  # user_data
    )),
    ('nghttp2_on_frame_recv_callback', c_int, (
        POINTER(nghttp2_session),  # session
        POINTER(nghttp2_frame),  # frame
        c_void_p,  # user_data
    )),
    ('nghttp2_on_data_chunk_recv_callback', c_int, (
        POINTER(nghttp2_session),  # session
        c_uint8,  # flags
        c_int32,  # stream_id
        c_uint8_p,  # data
        c_size_t,  # length
        c_void_p,  # user_data
    )),
    ('nghttp2_on_frame_send_callback', c_int, (
        POINTER(nghttp2_session),  # session
        POINTER(nghttp2_frame),  # frame
        c_void_p,  # user_data
    )),
    ('nghttp2_on_frame_not_send_callback', c_int, (
        POINTER(nghttp2_session),  # session
        POINTER(nghttp2_frame),  # frame
        c_int,  # lib_error_code
        c_void_p,  # user_data
    )),
    ('nghttp2_on_stream_close_callback', c_int, (
        POINTER(nghttp2_session),  # session
        c_int32,  # stream_id
        c_uint32,  # error_code
        c_void_p,  # user_data
    )),
    ('nghttp2_on_begin_headers_callback', c_int, (
        POINTER(nghttp2_session),  # session
        POINTER(nghttp2_frame),  # frame
        c_void_p,  # user_data
    )),
    ('nghttp2_on_header_callback', c_int, (
        POINTER(nghttp2_session),  # session
        POINTER(nghttp2_frame),  # frame
        c_uint8_p,  # name
        c_size_t,  # namelen
        c_uint8_p,  # value
        c_size_t,  # valuelen
        c_uint8,  # flags
        c_void_p,  # user_data
    )),
])


### Structs and unions


@declare_struct
class nghttp2_info(Structure):
    _fields_ = [
        ('age', c_int),
        ('version_num', c_int),
        ('version_str', c_char_p),
        ('proto_str', c_char_p),
    ]


@declare_struct
class nghttp2_nv(Structure):
    _fields_ = [
        ('name', c_uint8_p),
        ('value', c_uint8_p),
        ('namelen', c_size_t),
        ('valuelen', c_size_t),
        ('flags', c_uint8),
    ]


@declare_struct
class nghttp2_frame_hd(Structure):
    _fields_ = [
        ('length', c_size_t),
        ('stream_id', c_int32),
        ('type', c_uint8),
        ('flags', c_uint8),
        ('reserved', c_uint8),
    ]


nghttp2_data_source._fields_ = [
    ('fd', c_int),
    ('ptr', c_void_p),
]


@declare_struct
class nghttp2_data_provider(Structure):
    _fields_ = [
        ('source', nghttp2_data_source),
        ('read_callback', nghttp2_data_source_read_callback),
    ]


@declare_struct
class nghttp2_data(Structure):
    _fields_ = [
        ('hd', nghttp2_frame_hd),
        ('padlen', c_size_t),
    ]


@declare_struct
class nghttp2_priority_spec(Structure):
    _fields_ = [
        ('stream_id', c_int32),
        ('weight', c_int32),
        ('exclusive', c_uint8),
    ]


@declare_struct
class nghttp2_headers(Structure):
    _fields_ = [
        ('hd', nghttp2_frame_hd),
        ('padlen', c_size_t),
        ('pri_spec', nghttp2_priority_spec),
        ('nva', POINTER(nghttp2_nv)),
        ('nvlen', c_size_t),
        ('cat', c_enum),  # nghttp2_headers_category
    ]


@declare_struct
class nghttp2_rst_stream(Structure):
    _fields_ = [
        ('hd', nghttp2_frame_hd),
        ('error_code', c_uint32),
    ]


@declare_struct
class nghttp2_settings_entry(Structure):
    _fields_ = [
        ('settings_id', c_int32),
        ('value', c_uint32),
    ]


@declare_struct
class nghttp2_push_promise(Structure):
    _fields_ = [
        ('hd', nghttp2_frame_hd),
        ('padlen', c_size_t),
        ('nva', POINTER(nghttp2_nv)),
        ('nvlen', c_size_t),
        ('promised_stream_id', c_int32),
        ('reserved', c_uint8),
    ]


@declare_struct
class nghttp2_goaway(Structure):
    _fields_ = [
        ('hd', nghttp2_frame_hd),
        ('last_stream_id', c_int32),
        ('error_code', c_uint32),
        ('opaque_data', c_uint8_p),
        ('opaque_data_len', c_size_t),
        ('reserved', c_uint8),
    ]


nghttp2_frame._fields_ = [
    ('hd', nghttp2_frame_hd),
    ('data', nghttp2_data),
    ('headers', nghttp2_headers),
    ('rst_stream', nghttp2_rst_stream),
    ('push_promise', nghttp2_push_promise),
    ('goaway', nghttp2_goaway),
]


@declare_struct
class nghttp2_session_callbacks(Structure):
    pass


### Functions


declare_functions([
    ('nghttp2_session_callbacks_new', c_int, (
        POINTER(POINTER(nghttp2_session_callbacks)),  # callbacks_ptr
    )),
    ('nghttp2_session_server_new', c_int, (
        POINTER(POINTER(nghttp2_session)),  # session_ptr
        POINTER(nghttp2_session_callbacks),  # callbacks
        c_void_p,  # user_data
    )),
    ('nghttp2_session_mem_send', c_ssize_t, (
        POINTER(nghttp2_session),  # session
        POINTER(c_uint8_p),  # data_ptr
    )),
    ('nghttp2_session_mem_recv', c_ssize_t, (
        POINTER(nghttp2_session),  # session
        c_uint8_p,  # data
        c_size_t,  # datalen
    )),
    ('nghttp2_session_get_stream_remote_close', c_int, (
        POINTER(nghttp2_session),  # session
        c_int32,  # stream_id
    )),
    ('nghttp2_session_terminate_session', c_int, (
        POINTER(nghttp2_session),  # session
        c_uint32,  # error_code
    )),
    ('nghttp2_submit_response', c_int, (
        POINTER(nghttp2_session),  # session
        c_int32,  # stream_id
        POINTER(nghttp2_nv),  # nva
        c_size_t,  # nvlen
        POINTER(nghttp2_data_provider),  # data_prd
    )),
    ('nghttp2_submit_rst_stream', c_int, (
        POINTER(nghttp2_session),  # session
        c_uint8,  # flags
        c_int32,  # stream_id
        c_uint32,  # error_code
    )),
    ('nghttp2_submit_settings', c_int, (
        POINTER(nghttp2_session),  # session
        c_uint8,  # flags
        POINTER(nghttp2_settings_entry),  # iv
        c_size_t,  # niv
    )),
    ('nghttp2_submit_push_promise', c_int, (
        POINTER(nghttp2_session),  # session
        c_uint8,  # flags
        c_int32,  # stream_id
        POINTER(nghttp2_nv),  # nva
        c_size_t,  # nvlen
        c_void_p,  # stream_user_data
    )),
])


declare_unchecked_functions([
    ('nghttp2_session_callbacks_del', None, (
        POINTER(nghttp2_session_callbacks),  # callbacks
    )),
    ('nghttp2_session_callbacks_set_on_frame_recv_callback', None, (
        POINTER(nghttp2_session_callbacks),  # cbs
        nghttp2_on_frame_recv_callback,  # on_frame_recv_callback
    )),
    ('nghttp2_session_callbacks_set_on_data_chunk_recv_callback', None, (
        POINTER(nghttp2_session_callbacks),  # cbs
        nghttp2_on_data_chunk_recv_callback,  # on_data_chunk_recv_callback
    )),
    ('nghttp2_session_callbacks_set_on_frame_send_callback', None, (
        POINTER(nghttp2_session_callbacks),  # cbs
        nghttp2_on_frame_send_callback,  # on_frame_send_callback
    )),
    ('nghttp2_session_callbacks_set_on_frame_not_send_callback', None, (
        POINTER(nghttp2_session_callbacks),  # cbs
        nghttp2_on_frame_not_send_callback,  # on_frame_not_send_callback
    )),
    ('nghttp2_session_callbacks_set_on_stream_close_callback', None, (
        POINTER(nghttp2_session_callbacks),  # cbs
        nghttp2_on_stream_close_callback,  # on_stream_close_callback
    )),
    ('nghttp2_session_callbacks_set_on_begin_headers_callback', None, (
        POINTER(nghttp2_session_callbacks),  # cbs
        nghttp2_on_begin_headers_callback,  # on_begin_headers_callback
    )),
    ('nghttp2_session_callbacks_set_on_header_callback', None, (
        POINTER(nghttp2_session_callbacks),  # cbs
        nghttp2_on_header_callback,  # on_header_callback
    )),
    ('nghttp2_session_del', None, (
        POINTER(nghttp2_session),  # session
    )),
    ('nghttp2_session_want_read', c_int, (
        POINTER(nghttp2_session),  # session
    )),
    ('nghttp2_session_want_write', c_int, (
        POINTER(nghttp2_session),  # session
    )),
    ('nghttp2_strerror', c_char_p, (
        c_int,  # lib_error_code
    )),
    ('nghttp2_version', POINTER(nghttp2_info), (
        c_int,  # least_version
    )),
])
