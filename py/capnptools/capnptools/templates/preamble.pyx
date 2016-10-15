# Generated at ${now.isoformat()} - DO NOT EDIT!

__all__ = [
    'FlatArrayMessageReader',
    'StreamFdMessageReader',
    'MallocMessageBuilder',
]

import enum
import sys
import types
from collections import OrderedDict, Sequence, MutableSequence

from cpython.pycapsule cimport PyCapsule_New, PyCapsule_GetPointer
from cython.operator cimport dereference
from libc.stdint cimport int8_t, int16_t, int32_t, int64_t, uint8_t, uint16_t, uint32_t, uint64_t
from libcpp cimport bool

cdef extern from "<capnp/common.h>":
    cdef cppclass capnp__word 'capnp::word':
        pass
    cdef cppclass capnp__Void 'capnp::Void':
        pass

cdef extern from "<kj/array.h>":
    cdef cppclass kj__ArrayPtr 'kj::ArrayPtr<const capnp::word>':
        kj__ArrayPtr(const capnp__word* begin, size_t size) except +

cdef extern from "<capnp/blob.h>":
    cdef cppclass capnp__Text__Reader 'capnp::Text::Reader':
        capnp__Text__Reader() except +
        capnp__Text__Reader(const char* value, size_t size) except +
        const char* cStr() except +
    cdef cppclass capnp__Text__Builder 'capnp::Text::Builder':
        capnp__Text__Builder() except +
        capnp__Text__Builder(char* value, size_t size) except +
        const char* cStr() except +
        char& operator[](size_t index) except +
    cdef cppclass capnp__Data__Reader 'capnp::Data::Reader':
        capnp__Data__Reader() except +
        capnp__Data__Reader(const char* value, size_t size) except +
        const char* cStr() except +
    cdef cppclass capnp__Data__Builder 'capnp::Data::Builder':
        capnp__Data__Builder() except +
        capnp__Data__Builder(char* value, size_t size) except +
        const char* cStr() except +
        char& operator[](size_t index) except +
% if list_types:

cdef extern from "<capnp/list.h>":
    % for list_type in list_types:
    % for level in range(1, list_type.level + 1):
##  List reader class
    cdef cppclass ${list_type.get_cython_classname(node_table, level)}__Reader '${"capnp::List<" * level}${list_type.get_cc_classname(node_table, level)}${">" * level}::Reader':
        unsigned int size() except +
        % if level == 1 and (list_type.is_primitive or list_type.is_enum):
        ${list_type.get_cython_classname(node_table, level - 1)} operator[](unsigned int index) except +
        % else:
        ${list_type.get_cython_classname(node_table, level - 1)}__Reader operator[](unsigned int index) except +
        % endif
##  List builder class
    cdef cppclass ${list_type.get_cython_classname(node_table, level)}__Builder '${"capnp::List<" * level}${list_type.get_cc_classname(node_table, level)}${">" * level}::Builder':
        ${list_type.get_cython_classname(node_table, level)}__Reader asReader() except +
        unsigned int size() except +
##      List of primitives or enums
        % if level == 1 and (list_type.is_primitive or list_type.is_enum):
        ${list_type.get_cython_classname(node_table, level - 1)} operator[](unsigned int index) except +
        void set(unsigned int index, ${list_type.get_cython_classname(node_table, level - 1)} value) except +
##      List of structs
        % elif level == 1 and list_type.is_struct:
        ${list_type.get_cython_classname(node_table, level - 1)}__Builder operator[](unsigned int index) except +
##      List of lists or blobs
        % elif level > 1 or list_type.is_blob:
        ${list_type.get_cython_classname(node_table, level - 1)}__Builder operator[](unsigned int index) except +
        ${list_type.get_cython_classname(node_table, level - 1)}__Builder init(unsigned int index, unsigned int size) except +
        void set(unsigned int index, ${list_type.get_cython_classname(node_table, level - 1)}__Reader value) except +
        % endif
    % endfor
    % endfor
% endif
