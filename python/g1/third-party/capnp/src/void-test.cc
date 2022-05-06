#include <boost/python/def.hpp>

#include <capnp/common.h>

namespace capnp_python {
namespace test {

namespace {

capnp::Void takeVoid(capnp::Void v) {
  return v;
}

}  // namespace

void defineVoidTypeForTesting(void) {
  boost::python::def("takeVoid", takeVoid);
}

}  // namespace test
}  // namespace capnp_python
