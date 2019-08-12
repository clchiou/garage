#include <boost/python/class.hpp>
#include <boost/python/def.hpp>

#include <capnp/dynamic.h>
#include <capnp/serialize-text.h>

namespace capnp_python {

void defineTextCodecTypes(void) {
  // NOTE: It is interesting that `~TextCodec` is declared as
  // noexcept(true), rather than noexcept(false); so no extra wrapping
  // for value type is needed.
  boost::python::class_<capnp::TextCodec>("TextCodec", boost::python::init<>())
      .def("setPrettyPrint", &capnp::TextCodec::setPrettyPrint)
      .def(
          "encode",
          static_cast<kj::String (capnp::TextCodec::*)(capnp::DynamicValue::Reader) const>(
              &capnp::TextCodec::encode))
      .def(
          "decode",
          static_cast<void (capnp::TextCodec::*)(kj::StringPtr, capnp::DynamicStruct::Builder)
                          const>(&capnp::TextCodec::decode));
}

}  // namespace capnp_python
