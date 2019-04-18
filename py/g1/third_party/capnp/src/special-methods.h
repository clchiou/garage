#ifndef CAPNP_PYTHON_SPECIAL_METHODS_H_
#define CAPNP_PYTHON_SPECIAL_METHODS_H_

#include <Python.h>

#include <boost/python/errors.hpp>

namespace capnp_python {

// Helpers for exposing member functions or Python special methods.
template <typename T, typename E>
struct SpecialMethods {

  // C++ does not allow taking member function pointer to constructor.
  // So we need an indirection.
  //
  // For now only an one-argument constructor is added.
  static T constructor(E arg) { return T(arg); }

  // Wrap operator[] to satisfy Python __getitem__ interface.
  static E getitem(T& self, size_t index) {
    if (index >= self.size()) {
      PyErr_SetString(PyExc_IndexError, "index out of range");
      boost::python::throw_error_already_set();
    }
    return self[index];
  }
};

}  // namespace capnp_python

#endif  // CAPNP_PYTHON_SPECIAL_METHODS_H_
