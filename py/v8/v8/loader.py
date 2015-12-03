__all__ = [
    'BOOL',
    'load',
]

import logging
from ctypes import (
    cdll,
    c_char_p,
    c_void_p,
    c_double,
    c_int,
    c_ubyte,
    c_uint,
    POINTER,
)


LOG = logging.getLogger(__name__)


BOOL = c_ubyte


FUNC_DECLS = (
    # v8::Context
    ('v8_context_new', [c_void_p], c_void_p),
    ('v8_context_enter', [c_void_p], None),
    ('v8_context_global', [c_void_p], c_void_p),
    ('v8_context_exit', [c_void_p], None),
    ('v8_context_delete', [c_void_p], None),
    # v8::HandleScope
    ('v8_handle_scope_new', [c_void_p], c_void_p),
    ('v8_handle_scope_delete', [c_void_p], None),
    # v8::Isolate
    ('v8_isolate_new', [c_void_p], c_void_p),
    ('v8_isolate_enter', [c_void_p], None),
    ('v8_isolate_exit', [c_void_p], None),
    ('v8_isolate_dispose', [c_void_p], None),
    # v8::Isolate::CreateParams
    ('v8_isolate_create_params_new', [], c_void_p),
    ('v8_isolate_create_params_delete', [c_void_p], None),
    # v8::V8
    ('v8_initialize', [], BOOL),
    ('v8_initialize_icu', [c_char_p], BOOL),
    ('v8_initialize_external_startup_data', [c_char_p], None),
    ('v8_initialize_external_startup_data2', [c_char_p, c_char_p], None),
    ('v8_initialize_platform', [c_void_p], None),
    ('v8_dispose', [], BOOL),
    ('v8_shutdown_platform', [], None),
    # v8::platform
    ('v8_platform_create_default_platform', [c_int], c_void_p),
    ('v8_platform_delete', [c_void_p], None),
    # JavaScript values.
    # v8::Array
    ('v8_array_cast_from', [c_void_p], c_void_p),
    ('v8_array_length', [c_void_p], c_uint),
    ('v8_array_get', [c_void_p, c_void_p, c_uint], c_void_p),
    ('v8_array_delete', [c_void_p], None),
    # v8::Map
    ('v8_map_cast_from', [c_void_p], c_void_p),
    ('v8_map_as_array', [c_void_p], c_void_p),
    ('v8_map_delete', [c_void_p], None),
    # v8::Number
    ('v8_number_cast_from', [c_void_p], c_double),
    # v8::Object
    ('v8_object_get_property_names', [c_void_p, c_void_p], c_void_p),
    ('v8_object_has', [c_void_p, c_void_p, c_void_p, POINTER(BOOL)], BOOL),
    ('v8_object_get', [c_void_p, c_void_p, c_void_p], c_void_p),
    ('v8_object_set',
     [c_void_p, c_void_p, c_void_p, c_void_p, POINTER(BOOL)],
     BOOL),
    ('v8_object_del', [c_void_p, c_void_p, c_void_p, POINTER(BOOL)], BOOL),
    ('v8_object_delete', [c_void_p], None),
    # v8::Script
    ('v8_script_compile', [c_void_p, c_void_p], c_void_p),
    ('v8_script_run', [c_void_p, c_void_p], c_void_p),
    ('v8_script_delete', [c_void_p], None),
    # v8::String
    ('v8_string_new_from_utf8', [c_void_p, c_char_p], c_void_p),
    ('v8_string_delete', [c_void_p], None),
    # v8::String::Utf8Value
    ('v8_utf8_value_new', [c_void_p], c_void_p),
    ('v8_utf8_value_cstr', [c_void_p], c_char_p),
    ('v8_utf8_value_delete', [c_void_p], None),
    # v8::Value
    ('v8_value_is_array', [c_void_p], BOOL),
    ('v8_value_is_map', [c_void_p], BOOL),
    ('v8_value_is_object', [c_void_p], BOOL),
    ('v8_value_is_string', [c_void_p], BOOL),
    ('v8_value_is_number', [c_void_p], BOOL),
    ('v8_value_is_int32', [c_void_p], BOOL),
    ('v8_value_is_uint32', [c_void_p], BOOL),
    ('v8_value_delete', [c_void_p], None),
)


def load():
    LOG.info('load libv8_cabi.so')
    funcs = {}
    lib = cdll.LoadLibrary('libv8_cabi.so')
    for func_decl in FUNC_DECLS:
        name, argtypes, restype = func_decl
        func = getattr(lib, name)
        if argtypes:
            func.argtypes = argtypes
        if restype:
            func.restype = restype
        funcs[name] = func
    return funcs
