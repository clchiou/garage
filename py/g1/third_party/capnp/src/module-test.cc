#include <boost/python/module.hpp>

namespace capnp_python {
namespace test {

void defineResourceTypesForTesting(void);
void defineSchemaTypesForTesting(void);
void defineStringTypesForTesting(void);
void defineValueTypesForTesting(void);
void defineVoidTypeForTesting(void);

}  // namespace test
}  // namespace capnp_python

BOOST_PYTHON_MODULE(_capnp_test) {
  capnp_python::test::defineResourceTypesForTesting();
  capnp_python::test::defineSchemaTypesForTesting();
  capnp_python::test::defineStringTypesForTesting();
  capnp_python::test::defineValueTypesForTesting();
  capnp_python::test::defineVoidTypeForTesting();
}
