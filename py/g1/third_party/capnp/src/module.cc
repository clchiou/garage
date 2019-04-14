#include <boost/python/module.hpp>

namespace capnp_python {

void defineStringTypes(void);
void defineVoidType(void);

}  // namespace capnp_python

BOOST_PYTHON_MODULE(_capnp) {
  capnp_python::defineStringTypes();
  capnp_python::defineVoidType();
}
