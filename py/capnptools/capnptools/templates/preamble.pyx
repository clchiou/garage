# Generated at ${now.isoformat()} - DO NOT EDIT!

import enum
from cpython.pycapsule cimport PyCapsule_New, PyCapsule_GetPointer
from cython.operator cimport dereference, preincrement
from libc.stdint cimport int8_t, int16_t, int32_t, int64_t, uint8_t, uint16_t, uint32_t, uint64_t
from libcpp cimport bool

cdef extern from "<capnp/common.h>":
    cdef cppclass capnp__word 'capnp::word':
        pass

cdef extern from "<kj/array.h>":
    cdef cppclass kj__ArrayPtr 'kj::ArrayPtr<const capnp::word>':
        kj__ArrayPtr(const capnp__word* begin, size_t size) except +

cdef extern from "<capnp/generated-header-support.h>":
    cdef cppclass capnp__Void 'capnp::Void':
        pass
    cdef cppclass capnp__Text__Reader 'capnp::Text::Reader':
        const char* cStr() except +
    cdef cppclass capnp__Text__Builder 'capnp::Text::Builder':
        const char* cStr() except +
    cdef cppclass capnp__Data__Reader 'capnp::Data::Reader':
        pass
    cdef cppclass capnp__Data__Builder 'capnp::Data::Builder':
        pass
    % for list_type in list_types:
    cdef cppclass ${list_type.get_cython_classname(node_table)}__Reader '${list_type.get_cc_classname(node_table)}::Reader':
        pass
    cdef cppclass ${list_type.get_cython_classname(node_table)}__Builder '${list_type.get_cc_classname(node_table)}::Builder':
        pass
    % endfor
