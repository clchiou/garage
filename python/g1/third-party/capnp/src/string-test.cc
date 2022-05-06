#include <boost/python/class.hpp>
#include <boost/python/def.hpp>

#include <kj/common.h>
#include <kj/string-tree.h>
#include <kj/string.h>

#include <capnp/blob.h>
#include <capnp/common.h>

namespace capnp_python {
namespace test {

namespace {

template <typename E>
struct ArrayPtrHolder {
  kj::ArrayPtr<const E> array;
  kj::ArrayPtr<const E> getConst() { return array; }
  kj::ArrayPtr<E> get() { return kj::ArrayPtr<E>(const_cast<E*>(array.begin()), array.size()); }
  capnp::Data::Reader asReader() const { return array; }
};

struct StringPtrHolder {
  kj::StringPtr array;
  kj::StringPtr get() const { return array; }
  void set(kj::StringPtr other) { array = other; }
  size_t size() const { return array.size(); }
  capnp::Text::Reader asReader() const { return array; }
};

template <typename S, typename T>
struct Maker {
  static T make1(S array) { return T(array.begin(), array.size()); }
  static T make2(S array) { return T(const_cast<char*>(array.begin()), array.size()); }
};

kj::StringTree toStringTree(StringPtrHolder holder) {
  return kj::StringTree(kj::heapString(holder.array));
}

}  // namespace

void defineStringTypesForTesting(void) {

  boost::python::class_<ArrayPtrHolder<kj::byte>>("ArrayPtrBytesHolder")
      .def_readwrite("array", &ArrayPtrHolder<kj::byte>::array)
      .def("getConst", &ArrayPtrHolder<kj::byte>::getConst)
      .def("get", &ArrayPtrHolder<kj::byte>::get)
      .def("asReader", &ArrayPtrHolder<kj::byte>::asReader);

  boost::python::class_<ArrayPtrHolder<capnp::word>>("ArrayPtrWordsHolder")
      .def_readwrite("array", &ArrayPtrHolder<capnp::word>::array)
      .def("getConst", &ArrayPtrHolder<capnp::word>::getConst)
      .def("get", &ArrayPtrHolder<capnp::word>::get);

  boost::python::class_<StringPtrHolder>("StringPtrHolder")
      .def("get", &StringPtrHolder::get)
      .def("set", &StringPtrHolder::set)
      .def("size", &StringPtrHolder::size)
      .def("asReader", &StringPtrHolder::asReader);

  boost::python::def(
      "makeDataReader", &Maker<kj::ArrayPtr<const kj::byte>, capnp::Data::Reader>::make1);
  boost::python::def(
      "makeDataBuilder", &Maker<kj::ArrayPtr<kj::byte>, capnp::Data::Builder>::make1);

  boost::python::def("makeTextReader", &Maker<kj::StringPtr, capnp::Text::Reader>::make1);
  boost::python::def("makeTextBuilder", &Maker<kj::StringPtr, capnp::Text::Builder>::make2);

  boost::python::def("toStringTree", toStringTree);
}

}  // namespace test
}  // namespace capnp_python
