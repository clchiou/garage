#ifndef CAPNP_PYTHON_MAYBE_H_
#define CAPNP_PYTHON_MAYBE_H_

#include <Python.h>

#include <boost/python/to_python_converter.hpp>

#include <kj/common.h>

namespace capnp_python {

// Convert kj::Maybe<T> to Python None or T.
template <typename T>
struct MaybeToPython {
  static PyObject* convert(kj::Maybe<T> maybe) {
    KJ_IF_MAYBE(ptr, maybe) {
      boost::python::object o(*ptr);
      return boost::python::incref(o.ptr());
    }
    else {
      Py_RETURN_NONE;
    }
  }
};

template <typename T>
using MaybeToPythonConverter = boost::python::to_python_converter<kj::Maybe<T>, MaybeToPython<T>>;

}  // namespace capnp_python

#endif  // CAPNP_PYTHON_MAYBE_H_
