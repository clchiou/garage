#include <boost/python/class.hpp>

#include <kj/common.h>
#include <kj/string.h>

#include <capnp/common.h>

namespace capnp_python {
namespace test {

namespace {

template <typename E>
struct ArrayPtrHolder {
  kj::ArrayPtr<const E> array;
  kj::ArrayPtr<const E> getConst() { return array; }
  kj::ArrayPtr<E> get() { return kj::ArrayPtr<E>(const_cast<E*>(array.begin()), array.size()); }
};

struct StringPtrHolder {
  kj::StringPtr array;
  kj::StringPtr get() const { return array; }
  void set(kj::StringPtr other) { array = other; }
  size_t size() const { return array.size(); }
};

}  // namespace

void defineStringTypesForTesting(void) {

  boost::python::class_<ArrayPtrHolder<kj::byte>>("ArrayPtrBytesHolder")
      .def_readwrite("array", &ArrayPtrHolder<kj::byte>::array)
      .def("getConst", &ArrayPtrHolder<kj::byte>::getConst)
      .def("get", &ArrayPtrHolder<kj::byte>::get);

  boost::python::class_<ArrayPtrHolder<capnp::word>>("ArrayPtrWordsHolder")
      .def_readwrite("array", &ArrayPtrHolder<capnp::word>::array)
      .def("getConst", &ArrayPtrHolder<capnp::word>::getConst)
      .def("get", &ArrayPtrHolder<capnp::word>::get);

  boost::python::class_<StringPtrHolder>("StringPtrHolder")
      .def("get", &StringPtrHolder::get)
      .def("set", &StringPtrHolder::set)
      .def("size", &StringPtrHolder::size);
}

}  // namespace test
}  // namespace capnp_python
