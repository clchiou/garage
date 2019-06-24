#include <boost/python/module.hpp>

namespace capnp_python {

void defineAnyTypes(void);
void defineArrayTypes(void);
void defineDynamicValueTypes(void);
void defineMessageTypes(void);
void defineSchemaLoaderType(void);
void defineSchemaTypes(void);
void defineStringTypes(void);
void defineTextCodecTypes(void);
void defineVoidType(void);

}  // namespace capnp_python

BOOST_PYTHON_MODULE(_capnp) {
  capnp_python::defineAnyTypes();
  capnp_python::defineArrayTypes();
  capnp_python::defineDynamicValueTypes();
  capnp_python::defineMessageTypes();
  capnp_python::defineSchemaLoaderType();
  capnp_python::defineSchemaTypes();
  capnp_python::defineStringTypes();
  capnp_python::defineTextCodecTypes();
  capnp_python::defineVoidType();
}
