"""nghttp2 binding."""

# We are being clever and have to disable some linter warnings.
# pylint: disable=expression-not-assigned
# pylint: disable=undefined-variable

__all__ = [
    'Nghttp2Error',
    # Macro constants.
    'NGHTTP2_INITIAL_WINDOW_SIZE',
    'NGHTTP2_PROTO_VERSION_ID',
    # Enums.
    'nghttp2_data_flag',
    'nghttp2_error',
    'nghttp2_error_code',
    'nghttp2_flag',
    'nghttp2_frame_type',
    'nghttp2_headers_category',
    'nghttp2_nv_flag',
    'nghttp2_settings_id',
    # More symbol will be added dynamically.
]

from ctypes import (
    cdll,
    # Complex types.
    CFUNCTYPE,
    POINTER,
    Structure,
    Union,
    # Primitive types.
    c_char_p,
    c_int,
    c_int32,
    c_size_t,
    c_ssize_t,
    c_uint32,
    c_uint8,
    c_void_p,
)
import enum

from g1.bases.assertions import ASSERT

LIBNGHTTP2 = cdll.LoadLibrary('libnghttp2.so')

# Represent not NULL-terminated strings.
c_uint8_p = c_void_p

# NOTE: We will assume all storage types for C enum is int (nghttp2 does
# not specify enum storage type).
c_enum = c_int


class Nghttp2Error(Exception):

    def __init__(self, error_code, message):
        super().__init__(message)
        self.error_code = error_code


def export_members(enum_type):
    """Export enum members to global scope."""
    globals().update(enum_type.__members__)
    __all__.extend(enum_type.__members__.keys())
    return enum_type


def export(*args):
    """Export value to global scope."""
    if len(args) == 2:
        name, value = args
        ASSERT.not_contains(globals(), name)[name] = value
    else:
        # It is called as a decorator.
        ASSERT.equal(len(args), 1)
        value = args[0]
        name = value.__name__
    __all__.append(name)
    return value


def make_checked(name, restype, argtypes):
    """Make a checked C function."""

    func = make_unchecked(name, restype, argtypes)

    def checked(*args):
        rc = func(*args)
        if rc < 0:
            message = nghttp2_strerror(rc).decode('utf-8')
            raise Nghttp2Error(rc, '%s: %s' % (name, message))
        return rc

    checked.__name__ = checked.__qualname__ = name

    return checked


def make_unchecked(name, restype, argtypes):
    """Make an unchecked C function."""
    func = getattr(LIBNGHTTP2, name)
    func.restype = restype
    func.argtypes = argtypes
    return func


#
# Macro constants.
#

NGHTTP2_PROTO_VERSION_ID = 'h2'

NGHTTP2_INITIAL_WINDOW_SIZE = (1 << 16) - 1

#
# Enums.
#


@export_members
class nghttp2_error(enum.IntEnum):
    NGHTTP2_ERR_DEFERRED = -508
    NGHTTP2_ERR_TEMPORAL_CALLBACK_FAILURE = -521
    NGHTTP2_ERR_CALLBACK_FAILURE = -902
    NGHTTP2_ERR_BAD_CLIENT_MAGIC = -903


@export_members
class nghttp2_error_code(enum.IntEnum):
    NGHTTP2_NO_ERROR = 0x00
    NGHTTP2_INTERNAL_ERROR = 0x02
    NGHTTP2_SETTINGS_TIMEOUT = 0x04


@export_members
class nghttp2_flag(enum.IntEnum):
    NGHTTP2_FLAG_NONE = 0
    NGHTTP2_FLAG_END_STREAM = 0x01
    NGHTTP2_FLAG_END_HEADERS = 0x04
    NGHTTP2_FLAG_ACK = 0x01


@export_members
class nghttp2_frame_type(enum.IntEnum):
    NGHTTP2_DATA = 0x00
    NGHTTP2_HEADERS = 0x01
    NGHTTP2_SETTINGS = 0x04
    NGHTTP2_PUSH_PROMISE = 0x05


@export_members
class nghttp2_settings_id(enum.IntEnum):
    NGHTTP2_SETTINGS_MAX_CONCURRENT_STREAMS = 0x03
    NGHTTP2_SETTINGS_INITIAL_WINDOW_SIZE = 0x04
    NGHTTP2_SETTINGS_MAX_HEADER_LIST_SIZE = 0x06


@export_members
class nghttp2_headers_category(enum.IntEnum):
    NGHTTP2_HCAT_REQUEST = 0


@export_members
class nghttp2_data_flag(enum.IntFlag):
    NGHTTP2_DATA_FLAG_EOF = 0x01


@export_members
class nghttp2_nv_flag(enum.IntFlag):
    NGHTTP2_NV_FLAG_NONE = 0


#
# Structures and unions.
#


@export
class nghttp2_session(Structure):
    pass


@export
class nghttp2_data_source(Union):
    _fields_ = [
        ('fd', c_int),
        ('ptr', c_void_p),
    ]


@export
class nghttp2_frame_hd(Structure):
    _fields_ = [
        ('length', c_size_t),
        ('stream_id', c_int32),
        ('type', c_uint8),
        ('flags', c_uint8),
        ('reserved', c_uint8),
    ]


@export
class nghttp2_data(Structure):
    _fields_ = [
        ('hd', nghttp2_frame_hd),
        ('padlen', c_size_t),
    ]


@export
class nghttp2_nv(Structure):
    _fields_ = [
        ('name', c_uint8_p),
        ('value', c_uint8_p),
        ('namelen', c_size_t),
        ('valuelen', c_size_t),
        ('flags', c_uint8),
    ]


@export
class nghttp2_priority_spec(Structure):
    _fields_ = [
        ('stream_id', c_int32),
        ('weight', c_int32),
        ('exclusive', c_uint8),
    ]


@export
class nghttp2_headers(Structure):
    _fields_ = [
        ('hd', nghttp2_frame_hd),
        ('padlen', c_size_t),
        ('pri_spec', nghttp2_priority_spec),
        ('nva', POINTER(nghttp2_nv)),
        ('nvlen', c_size_t),
        ('cat', c_enum),  # nghttp2_headers_category
    ]


@export
class nghttp2_rst_stream(Structure):
    _fields_ = [
        ('hd', nghttp2_frame_hd),
        ('error_code', c_uint32),
    ]


@export
class nghttp2_push_promise(Structure):
    _fields_ = [
        ('hd', nghttp2_frame_hd),
        ('padlen', c_size_t),
        ('nva', POINTER(nghttp2_nv)),
        ('nvlen', c_size_t),
        ('promised_stream_id', c_int32),
        ('reserved', c_uint8),
    ]


@export
class nghttp2_goaway(Structure):
    _fields_ = [
        ('hd', nghttp2_frame_hd),
        ('last_stream_id', c_int32),
        ('error_code', c_uint32),
        ('opaque_data', c_uint8_p),
        ('opaque_data_len', c_size_t),
        ('reserved', c_uint8),
    ]


@export
class nghttp2_frame(Union):
    _fields_ = [
        ('hd', nghttp2_frame_hd),
        ('data', nghttp2_data),
        ('headers', nghttp2_headers),
        ('rst_stream', nghttp2_rst_stream),
        ('push_promise', nghttp2_push_promise),
        ('goaway', nghttp2_goaway),
    ]


@export
class nghttp2_info(Structure):
    _fields_ = [
        ('age', c_int),
        ('version_num', c_int),
        ('version_str', c_char_p),
        ('proto_str', c_char_p),
    ]


@export
class nghttp2_settings_entry(Structure):
    _fields_ = [
        ('settings_id', c_int32),
        ('value', c_uint32),
    ]


@export
class nghttp2_session_callbacks(Structure):
    pass


#
# Callbacks.
#

[
    export(name, CFUNCTYPE(restype, *argtypes))
    for name, restype, argtypes in [
        (
            'nghttp2_data_source_read_callback',
            c_ssize_t,
            (
                POINTER(nghttp2_session),  # session
                c_int32,  # stream_id
                c_uint8_p,  # buf
                c_size_t,  # length
                POINTER(c_uint32),  # data_flags
                POINTER(nghttp2_data_source),  # source
                c_void_p,  # user_data
            ),
        ),
        (
            'nghttp2_on_frame_recv_callback',
            c_int,
            (
                POINTER(nghttp2_session),  # session
                POINTER(nghttp2_frame),  # frame
                c_void_p,  # user_data
            ),
        ),
        (
            'nghttp2_on_data_chunk_recv_callback',
            c_int,
            (
                POINTER(nghttp2_session),  # session
                c_uint8,  # flags
                c_int32,  # stream_id
                c_uint8_p,  # data
                c_size_t,  # length
                c_void_p,  # user_data
            ),
        ),
        (
            'nghttp2_on_frame_send_callback',
            c_int,
            (
                POINTER(nghttp2_session),  # session
                POINTER(nghttp2_frame),  # frame
                c_void_p,  # user_data
            ),
        ),
        (
            'nghttp2_on_frame_not_send_callback',
            c_int,
            (
                POINTER(nghttp2_session),  # session
                POINTER(nghttp2_frame),  # frame
                c_int,  # lib_error_code
                c_void_p,  # user_data
            ),
        ),
        (
            'nghttp2_on_stream_close_callback',
            c_int,
            (
                POINTER(nghttp2_session),  # session
                c_int32,  # stream_id
                c_uint32,  # error_code
                c_void_p,  # user_data
            ),
        ),
        (
            'nghttp2_on_begin_headers_callback',
            c_int,
            (
                POINTER(nghttp2_session),  # session
                POINTER(nghttp2_frame),  # frame
                c_void_p,  # user_data
            ),
        ),
        (
            'nghttp2_on_header_callback',
            c_int,
            (
                POINTER(nghttp2_session),  # session
                POINTER(nghttp2_frame),  # frame
                c_uint8_p,  # name
                c_size_t,  # namelen
                c_uint8_p,  # value
                c_size_t,  # valuelen
                c_uint8,  # flags
                c_void_p,  # user_data
            ),
        ),
    ]
]


@export
class nghttp2_data_provider(Structure):
    _fields_ = [
        ('source', nghttp2_data_source),
        ('read_callback', nghttp2_data_source_read_callback),
    ]


#
# Functions.
#

[
    export(decl[0], make_checked(*decl)) for decl in [
        (
            'nghttp2_session_callbacks_new',
            c_int,
            (
                POINTER(POINTER(nghttp2_session_callbacks)),  # callbacks_ptr
            ),
        ),
        (
            'nghttp2_session_server_new',
            c_int,
            (
                POINTER(POINTER(nghttp2_session)),  # session_ptr
                POINTER(nghttp2_session_callbacks),  # callbacks
                c_void_p,  # user_data
            ),
        ),
        (
            'nghttp2_session_mem_send',
            c_ssize_t,
            (
                POINTER(nghttp2_session),  # session
                POINTER(c_uint8_p),  # data_ptr
            ),
        ),
        (
            'nghttp2_session_mem_recv',
            c_ssize_t,
            (
                POINTER(nghttp2_session),  # session
                c_uint8_p,  # data
                c_size_t,  # datalen
            ),
        ),
        (
            'nghttp2_session_resume_data',
            c_int,
            (
                POINTER(nghttp2_session),  # session
                c_int32,  # stream_id
            ),
        ),
        (
            'nghttp2_session_get_stream_remote_close',
            c_int,
            (
                POINTER(nghttp2_session),  # session
                c_int32,  # stream_id
            ),
        ),
        (
            'nghttp2_session_terminate_session',
            c_int,
            (
                POINTER(nghttp2_session),  # session
                c_uint32,  # error_code
            ),
        ),
        (
            'nghttp2_submit_response',
            c_int,
            (
                POINTER(nghttp2_session),  # session
                c_int32,  # stream_id
                POINTER(nghttp2_nv),  # nva
                c_size_t,  # nvlen
                POINTER(nghttp2_data_provider),  # data_prd
            ),
        ),
        (
            'nghttp2_submit_rst_stream',
            c_int,
            (
                POINTER(nghttp2_session),  # session
                c_uint8,  # flags
                c_int32,  # stream_id
                c_uint32,  # error_code
            ),
        ),
        (
            'nghttp2_submit_settings',
            c_int,
            (
                POINTER(nghttp2_session),  # session
                c_uint8,  # flags
                POINTER(nghttp2_settings_entry),  # iv
                c_size_t,  # niv
            ),
        ),
        (
            'nghttp2_submit_push_promise',
            c_int,
            (
                POINTER(nghttp2_session),  # session
                c_uint8,  # flags
                c_int32,  # stream_id
                POINTER(nghttp2_nv),  # nva
                c_size_t,  # nvlen
                c_void_p,  # stream_user_data
            ),
        ),
    ]
]

[
    export(decl[0], make_unchecked(*decl)) for decl in [
        (
            'nghttp2_session_callbacks_del',
            None,
            (
                POINTER(nghttp2_session_callbacks),  # callbacks
            ),
        ),
        (
            'nghttp2_session_callbacks_set_on_frame_recv_callback',
            None,
            (
                POINTER(nghttp2_session_callbacks),  # cbs
                nghttp2_on_frame_recv_callback,  # on_frame_recv_callback
            ),
        ),
        (
            'nghttp2_session_callbacks_set_on_data_chunk_recv_callback',
            None,
            (
                POINTER(nghttp2_session_callbacks),  # cbs
                nghttp2_on_data_chunk_recv_callback,
                # on_data_chunk_recv_callback
            ),
        ),
        (
            'nghttp2_session_callbacks_set_on_frame_send_callback',
            None,
            (
                POINTER(nghttp2_session_callbacks),  # cbs
                nghttp2_on_frame_send_callback,  # on_frame_send_callback
            ),
        ),
        (
            'nghttp2_session_callbacks_set_on_frame_not_send_callback',
            None,
            (
                POINTER(nghttp2_session_callbacks),  # cbs
                nghttp2_on_frame_not_send_callback,
                # on_frame_not_send_callback
            ),
        ),
        (
            'nghttp2_session_callbacks_set_on_stream_close_callback',
            None,
            (
                POINTER(nghttp2_session_callbacks),  # cbs
                nghttp2_on_stream_close_callback,  # on_stream_close_callback
            ),
        ),
        (
            'nghttp2_session_callbacks_set_on_begin_headers_callback',
            None,
            (
                POINTER(nghttp2_session_callbacks),  # cbs
                nghttp2_on_begin_headers_callback,  # on_begin_headers_callback
            ),
        ),
        (
            'nghttp2_session_callbacks_set_on_header_callback',
            None,
            (
                POINTER(nghttp2_session_callbacks),  # cbs
                nghttp2_on_header_callback,  # on_header_callback
            ),
        ),
        (
            'nghttp2_session_del',
            None,
            (
                POINTER(nghttp2_session),  # session
            ),
        ),
        (
            'nghttp2_session_want_read',
            c_int,
            (
                POINTER(nghttp2_session),  # session
            ),
        ),
        (
            'nghttp2_session_want_write',
            c_int,
            (
                POINTER(nghttp2_session),  # session
            ),
        ),
        (
            'nghttp2_strerror',
            c_char_p,
            (
                c_int,  # lib_error_code
            ),
        ),
        (
            'nghttp2_version',
            POINTER(nghttp2_info),
            (
                c_int,  # least_version
            ),
        ),
    ]
]
