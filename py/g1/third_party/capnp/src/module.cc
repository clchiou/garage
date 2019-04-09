#include <boost/python/module.hpp>

namespace capnp_python {

void defineStringTypes(void);

}  // namespace capnp_python

BOOST_PYTHON_MODULE(_capnp) {
  capnp_python::defineStringTypes();
}
