#include <boost/python/module.hpp>

namespace capnp_python {

void defineSchemaLoaderType(void);
void defineSchemaTypes(void);
void defineStringTypes(void);
void defineVoidType(void);

}  // namespace capnp_python

BOOST_PYTHON_MODULE(_capnp) {
  capnp_python::defineSchemaLoaderType();
  capnp_python::defineSchemaTypes();
  capnp_python::defineStringTypes();
  capnp_python::defineVoidType();
}
