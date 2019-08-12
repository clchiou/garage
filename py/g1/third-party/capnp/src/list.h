#ifndef CAPNP_PYTHON_LIST_H_
#define CAPNP_PYTHON_LIST_H_

#include <boost/python/class_fwd.hpp>

#include <capnp/list.h>

#include "special-methods.h"

namespace capnp_python {

template <typename E>
void defineListType(const char* name) {
  using Type = typename capnp::List<E>::Reader;
  boost::python::class_<Type>(name)
      .def("__len__", &Type::size)
      .def("__getitem__", &SpecialMethods<Type, typename E::Reader>::getitem)
      .def("totalSize", &Type::totalSize);
}

}  // namespace capnp_python

#endif  // CAPNP_PYTHON_LIST_H_
